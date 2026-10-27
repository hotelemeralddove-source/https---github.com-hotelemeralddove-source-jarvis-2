"""Search *inside* the files, not just their names.

`search.py` answers *"where is budget.xlsx?"*. This answers the harder, more useful
question: *"which of my files mentions the Hampi advance?"* — across Word, Excel,
PowerPoint, PDF, CSV, text and notes.

Three design rules, all of them learned from how badly this usually goes:

1. **Reuse the reader, do not re-invent it.** `reading.read()` already extracts text
   from docx/xlsx/pptx/pdf and OCRs images, with honest warnings. This module only
   *indexes* what that returns, so there is one extraction path to fix, not two.
2. **Never touch what it reads.** Opens read-only, writes exactly one index file in
   JARVIS's own data folder, skips symlinks and system folders, and caps everything
   (file size, files, chars) so a 40 GB folder cannot hang the app.
3. **Keep the receipts.** Every hit returns the file, the line number and the exact
   words around the match — so you can check it in one glance instead of trusting a
   score. A search that cannot show you why it answered is a search you learn to ignore.

Incremental by design: a re-index only re-reads files whose size or mtime changed, so
the second run over a big folder is near-instant ("no buffering" is a feature here too).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import config, reading

MAX_FILES = 2_500               # a document folder, not a whole filesystem
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_CHARS = 120_000             # per file, from reading.read()
STORE_CHARS = 6_000             # what is kept in the index per file
MAX_DEPTH = 8
CACHE_SECONDS = 900
SNIPPET = 180

SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg", "__pycache__", "venv", ".venv", "env",
    "site-packages", "windows", "winsxs", "$recycle.bin", "system volume information",
    "appdata", ".cache", ".npm", ".gradle", ".m2", "dist", "build", "out", "target",
    "library", "movies", "music", "pictures", "arcart", "arcshots",
}

# reading.kind_of() names, not extensions: .txt/.md/.log all come back as "text"
TEXT_KINDS = {"text", "data", "docx", "xlsx", "pptx", "pdf"}
MEDIA_KINDS = {"image", "gif", "audio", "video", "mp4", "wav"}

_CACHE: dict = {"built": 0.0, "files": [], "roots": [], "stats": {}}
_STOP = {"a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "my", "me",
         "is", "it", "that", "this", "which", "what", "where", "did", "i", "write",
         "written", "file", "files", "document", "documents", "say", "says", "mention",
         "mentions", "mentioned", "inside", "search", "find", "about", "contain",
         "contains", "with", "from", "any", "all", "have", "has"}


# ------------------------------------------------------------------ paths
def _index_path() -> Path:
    return Path(config.data_dir()) / "text_index.json"


def default_roots(user_home: str | Path | None = None) -> list[str]:
    """The folders a person actually keeps documents in. Nothing system-wide."""
    home = Path(os.environ.get("ARCDESK_USER_HOME") or user_home or Path.home())
    wanted = [home / "Documents", home / "Desktop", home / "Downloads", home / "Notes",
              Path(os.environ.get("ARCDESK_USER_HOME") or Path.home()) / "ArcNotes"]
    roots = [str(p) for p in wanted if p.is_dir()]
    if not roots and Path(home).is_dir():
        roots = [str(home)]
    return roots


def _walk(roots: list[str], limit_files: int = MAX_FILES) -> tuple[list[Path], int, int]:
    """Candidate files, breadth-first, with a hard cap. Returns (paths, seen, skipped_big)."""
    found: list[Path] = []
    seen = 0
    skipped_big = 0
    queue = [(Path(r).expanduser(), 0) for r in roots]
    while queue and len(found) < limit_files:
        folder, depth = queue.pop(0)
        if depth > MAX_DEPTH:
            continue
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.lower() in SKIP_DIRS or entry.name.startswith("."):
                        continue
                    queue.append((Path(entry.path), depth + 1))
                    continue
                name = entry.name.lower()
                if name.startswith("~$") or name.startswith("."):
                    continue
                seen += 1
                size = entry.stat().st_size
                if size == 0 or size > MAX_FILE_BYTES:
                    skipped_big += 1
                    continue
                if reading.kind_of(entry.path) not in TEXT_KINDS:
                    continue
                found.append(Path(entry.path))
                if len(found) >= limit_files:
                    break
            except OSError:
                continue
    return found, seen, skipped_big


# ------------------------------------------------------------------ index
def load(force: bool = False) -> dict:
    """The index in memory, reloaded from disk only when it is stale."""
    if not force and _CACHE.get("files") and time.time() - _CACHE.get("built", 0) < CACHE_SECONDS:
        return _CACHE
    path = _index_path()
    if not path.is_file():
        return {"built": 0.0, "files": [], "roots": [], "stats": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"built": 0.0, "files": [], "roots": [], "stats": {}}
    if not force and _CACHE.get("files") and time.time() - _CACHE.get("built", 0) < CACHE_SECONDS:
        return _CACHE
    _CACHE.update(data if isinstance(data, dict) else {})
    _CACHE.setdefault("files", [])
    return _CACHE


def index(roots: str | list[str] | None = None, limit_files: int = MAX_FILES,
          ocr: bool = False) -> dict:
    """Read the documents and remember their text. Incremental: unchanged files are kept.

    `ocr=True` also OCRs images, which is slow (a second per image) and is therefore
    off by default; the reply always says which mode ran.
    """
    if isinstance(roots, str):
        wanted = [r for r in re.split(r"[|,;]", roots) if r.strip()]
    else:
        wanted = list(roots or [])
    asked = [os.path.expanduser(r.strip()) for r in wanted if r and r.strip()]
    chosen = [r for r in asked if os.path.isdir(r)]
    if asked and not chosen:
        return {"built": _CACHE.get("built", 0), "files": _CACHE.get("files", []),
                "roots": asked, "seconds": 0.0, "stats": _CACHE.get("stats", {}),
                "error": f"nothing at {asked[0]} — is the disk plugged in?"}
    if not chosen:
        chosen = default_roots()

    cached = load(force=False)
    previous = {f["path"]: f for f in (cached.get("files") or [])}
    # Files that genuinely have no text (scans, binaries) are remembered too. Without
    # this, every re-index would re-read a 50 MB scanned PDF and try again — the exact
    # "waiting for nothing" that the whole wave is supposed to remove.
    previous_empty = {e["path"]: e for e in (cached.get("empty") or [])}
    kinds = set(TEXT_KINDS)
    if ocr:
        kinds |= MEDIA_KINDS

    started = time.time()
    candidates, seen, skipped_big = _walk(chosen, limit_files)
    files: list[dict] = []
    empty_list: list[dict] = []
    reread = kept = 0
    no_text: list[str] = []

    for path in candidates:
        try:
            stat = path.stat()
        except OSError:
            continue
        key = str(path)
        stamp = {"path": key, "mtime": int(stat.st_mtime), "size": stat.st_size}
        old = previous.get(key)
        if old and old.get("mtime") == stamp["mtime"] and old.get("size") == stamp["size"]:
            files.append(old)
            kept += 1
            continue
        known_empty = previous_empty.get(key)
        if known_empty and known_empty.get("mtime") == stamp["mtime"] \
                and known_empty.get("size") == stamp["size"]:
            empty_list.append(known_empty)
            no_text.append(Path(key).name)
            continue
        if reading.kind_of(key) not in kinds:
            continue
        try:
            doc = reading.read(key, limit=MAX_CHARS, ocr=ocr)
        except (OSError, PermissionError, ValueError) as exc:
            # On Windows a document that is open in Word/Excel is *locked*, and reading
            # it raises PermissionError. One locked file used to abort the whole index
            # (the worker then reported "failed"), which is how a perfectly normal
            # desktop made document search look broken. Skipped, named, and counted.
            empty_list.append({**stamp, "name": Path(key).name,
                               "why": f"{type(exc).__name__}: it is open in another app"})
            no_text.append(Path(key).name)
            continue
        reread += 1
        text = (doc.text or "").strip()
        if not text:
            reason = (doc.warnings[0] if doc.warnings else "no text layer")
            empty_list.append({**stamp, "name": Path(key).name, "why": reason})
            no_text.append(Path(key).name)
            continue
        files.append({
            "path": key,
            "name": Path(key).name,
            "kind": doc.kind,
            "mtime": int(stat.st_mtime),
            "size": stat.st_size,
            "text": text[:STORE_CHARS],
            "chars": len(text),
            "warnings": doc.warnings[:2],
        })

    data = {
        "built": time.time(),
        "roots": chosen,
        "files": files,
        "empty": empty_list,
        "stats": {
            "roots": len(chosen), "found": len(files), "seen": seen,
            "reread": reread, "unchanged": kept, "no_text": len(empty_list),
            "no_text_names": no_text[:8], "skipped_big": skipped_big,
            "no_text_why": {e["name"]: e.get("why", "") for e in empty_list[:5]},
            "ocr": bool(ocr), "capped": len(files) >= limit_files,
            "seconds": round(time.time() - started, 2),
        },
    }
    try:
        _index_path().parent.mkdir(parents=True, exist_ok=True)
        _index_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    _CACHE.update(data)
    return data


# ----------------------------------------------------------------- search
def tokens(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9'&.-]{1,}", (query or "").lower())
    return [w for w in words if w not in _STOP]


def _lines(text: str) -> list[str]:
    return [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]


def _snippet(text: str, needle: str, words: list[str]) -> tuple[str, int]:
    """The best line for this query, with its number. '' when the match is only in the name."""
    rows = _lines(text)
    lowered = [row.lower() for row in rows]
    if needle:
        for i, row in enumerate(lowered):
            if needle in row:
                return _trim(rows[i]), i + 1
    best, best_score, best_no = "", 0, 0
    for i, row in enumerate(lowered):
        score = sum(1 for w in words if w in row)
        if score > best_score:
            best, best_score, best_no = rows[i], score, i + 1
    return (_trim(best), best_no) if best else ("", 0)


def _trim(line: str, width: int = SNIPPET) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    return line if len(line) <= width else line[: width - 1] + "…"


def search(query: str, limit: int = 8) -> dict:
    """Score every indexed file for this query. Returns {hits, mode, total, note}."""
    words = tokens(query)
    needle = " ".join((query or "").lower().split())
    data = load()
    files = data.get("files") or []
    if not files:
        return {"hits": [], "mode": "empty", "total": 0,
                "note": "nothing indexed yet"}
    if not words and not needle:
        return {"hits": [], "mode": "empty", "total": 0, "note": "empty query"}

    scored = []
    for item in files:
        text = (item.get("text") or "").lower()
        name = (item.get("name") or "").lower()
        if not text and not name:
            continue
        phrase = 12 if needle and len(needle) > 2 and needle in text else 0
        name_phrase = 6 if needle and needle in name else 0
        have = [w for w in words if w in text or w in name]
        if not have and not phrase and not name_phrase:
            continue
        score = phrase + name_phrase + 3 * len(have)
        if words and len(have) == len(words):
            score += 6                      # a file with every word is a better hit
        scored.append((score, len(have), item, have))

    mode = "all"
    complete = [row for row in scored if words and len(row[3]) == len(words)]
    if words and complete:
        scored = complete
    elif words and scored:
        mode = "some"

    scored.sort(key=lambda row: (-row[0], -row[1], row[2].get("mtime", 0)))
    hits = []
    for score, _have, item, _words in scored[: max(1, int(limit))]:
        snippet, line_no = _snippet(item.get("text") or "", needle, words)
        size = item.get("size", 0)
        hits.append({"path": item["path"], "name": item["name"], "kind": item.get("kind", ""),
                     "line": line_no, "snippet": snippet, "score": score,
                     "size": f"{size} B" if size < 1024 else f"{size / 1024:.0f} KB",
                     "warnings": item.get("warnings") or []})
    return {"hits": hits, "mode": mode, "total": len(scored), "note": ""}


def results_text(query: str, limit: int = 8) -> str:
    """The reply for `search_inside` — every line checkable, nothing invented."""
    data = load()
    files = data.get("files") or []
    if not files:
        return ("I have not indexed your documents yet, so I have nothing to search. Say "
                "'index my documents' (read-only, Word/Excel/PDF/text) and I will look.")
    result = search(query, limit)
    hits = result["hits"]
    if not hits:
        stats = data.get("stats") or {}
        return (f"No document in my index mentions “{query}”.\n"
                f"  searched {len(files)} files from {', '.join(data.get('roots') or [])}\n"
                f"  not everything is searchable: {stats.get('no_text', 0)} file(s) had no "
                f"text layer (scanned PDFs, images) and were skipped\n"
                f"  say 'index my documents with ocr' if you want images read too — slower, "
                f"but it reads scans.")
    out = [f"{len(hits)} match(es) for “{query}” — {result['total']} file(s) contain "
           f"those words, showing the best {len(hits)}:"]
    if result["mode"] == "some":
        out[0] = (f"No file has all the words in “{query}”, so these are partial matches "
                  f"(best first):")
    for i, hit in enumerate(hits, 1):
        where = f"line {hit['line']}" if hit["line"] else "in the file name"
        out.append(f"  {i}. {hit['name']}  [{hit['kind']}, {hit['size']}, {where}]")
        if hit["snippet"]:
            out.append(f"     “{hit['snippet']}”")
        out.append(f"     {hit['path']}")
        if hit["warnings"]:
            out.append(f"     note: {hit['warnings'][0]}")
    out.append("")
    out.append("These are quotes from your own files — open one to check the context. "
               "Nothing was uploaded and nothing was modified.")
    return "\n".join(out)


def first_hit(query: str) -> dict | None:
    hits = search(query, 1)["hits"]
    return hits[0] if hits else None


# ------------------------------------------------------------------- meta
def stats() -> str:
    data = load()
    files = data.get("files") or []
    if not files:
        return ("No document index yet. Say 'index my documents' — it reads Word, Excel, "
                "PowerPoint, PDF, CSV and text from your own folders, read-only.")
    stat = data.get("stats") or {}
    kinds: dict[str, int] = {}
    for item in files:
        kinds[item.get("kind", "?")] = kinds.get(item.get("kind", "?"), 0) + 1
    when = time.strftime("%d %b %H:%M", time.localtime(data.get("built") or 0))
    spread = " · ".join(f"{n} {k}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]))
    return (f"{len(files)} searchable documents · {spread}\n"
            f"indexed {when} from {', '.join(data.get('roots') or [])}\n"
            f"last run: {stat.get('reread', 0)} re-read, {stat.get('unchanged', 0)} unchanged"
            + (" · capped at the file limit" if stat.get("capped") else "")
            + " · read-only, nothing was modified")


def forget() -> str:
    """Delete the index, never the documents."""
    path = _index_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return "There was no document index to forget."
    except OSError as exc:
        return f"ERROR: could not remove the index: {exc}"
    _CACHE.clear()
    _CACHE.update({"built": 0.0, "files": [], "roots": [], "stats": {}})
    return ("Forgot the document index. Your files were not touched — this only removed "
            "one cache file that JARVIS itself wrote.")
