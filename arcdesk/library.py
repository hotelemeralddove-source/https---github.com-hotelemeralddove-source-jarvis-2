"""Find the user's music and video — including on an external disk — and play it.

Two jobs, both boring on purpose:

1. **Index** every audio/video file in the usual places *and* on removable drives, into
   one small JSON file. Scanning is interruptible, skips system folders, and never
   opens, moves or rewrites a media file — it only stats them.
2. **Search** that index fast enough to feel instant (a linear scan over ~50k rows is
   ~10 ms in CPython), with a score that survives real filenames:
   ``03 - Ilaya Nila (Official Video) 320kbps.mp3`` matches "ilaya nila".

No tagging library is required. If ``mutagen`` happens to be installed the real
artist/title tags are used; otherwise the filename is parsed and ARC says so, rather
than inventing an artist.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

AUDIO_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".wma", ".aiff",
             ".alac", ".mid", ".amr"}
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv", ".ts",
             ".mpg", ".mpeg", ".3gp", ".ogv"}
MEDIA_EXT = AUDIO_EXT | VIDEO_EXT

SKIP_DIRS = {
    "windows", "winnt", "$recycle.bin", "system volume information", "recovery",
    "perflogs", "program files", "program files (x86)", "programdata", "appdata",
    "node_modules", ".git", ".cache", "__pycache__", "site-packages", "dist-packages",
    "proc", "sys", "dev", "run", "snap", "boot", "lost+found",
}
MAX_FILES = 60_000
MIN_BYTES = 8_000          # below this it is a thumbnail or a stub, not a song
MAX_DEPTH = 9
CACHE_SECONDS = 900

_CACHE: dict = {"built": 0, "tracks": []}


# --------------------------------------------------------------------- drives
def drives() -> list[dict]:
    """Real mount points, with a removable flag where the OS reports one.

    USB hard disks often report themselves as *fixed* on Windows, so every drive letter
    other than C: is offered as well — hiding an external disk because of a wrong flag
    would be exactly the kind of "it should be there" bug that wastes an afternoon.
    """
    found: list[dict] = []
    seen: set[str] = set()

    def add(path: str, label: str, removable: bool, total: int = 0) -> None:
        key = os.path.normcase(str(path)).rstrip("/\\")
        if not key or key in seen:
            return
        seen.add(key)
        found.append({"path": str(path), "label": label, "removable": removable,
                      "total_gb": round(total / 1e9, 1) if total else 0})

    try:
        import psutil
        for part in psutil.disk_partitions(all=False):
            opts = (part.opts or "").lower()
            removable = ("removable" in opts or "cdrom" in opts
                         or part.fstype.lower() in ("vfat", "exfat", "msdos", "fuseblk"))
            try:
                usage = psutil.disk_usage(part.mountpoint)
                total = usage.total
            except Exception:
                total = 0
            add(part.mountpoint, part.device or part.mountpoint, removable, total)
    except Exception:
        pass

    if os.name == "nt":
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{letter}:\\"
            if os.path.exists(root):
                try:
                    usage = shutil.disk_usage(root)
                    total = usage.total
                except Exception:
                    total = 0
                add(root, f"{letter}: drive", True, total)
    else:
        for base in ("/media", "/run/media", "/mnt", "/Volumes"):
            base_path = Path(base)
            if not base_path.is_dir():
                continue
            for child in list(base_path.iterdir())[:8]:
                if child.is_dir():
                    add(str(child), child.name, True)
    return found


def default_roots(include_drives: bool = True) -> list[str]:
    home = Path(os.environ.get("ARCDESK_USER_HOME") or Path.home())
    names = ("Music", "Videos", "Movies", "Downloads", "Desktop", "Pictures",
             "Songs", "Films")
    roots = [str(home / n) for n in names if (home / n).is_dir()]
    if not roots and home.is_dir():
        roots.append(str(home))
    if include_drives:
        for drive in drives():
            if drive["path"] not in roots:
                roots.append(drive["path"])
    return roots[:10]


def _index_path() -> Path:
    from . import config
    return config.data_dir() / "media_index.json"


# ---------------------------------------------------------------------- index
def _clean_name(stem: str) -> str:
    """Strip the junk that file names carry: [320kbps], (Official Video), _hd, dots."""
    text = stem.replace("_", " ").replace(".", " ")
    text = re.sub(r"[\[\(\{][^\]\)\}]*[\]\)\}]", " ", text)
    text = re.sub(r"\b(1080p|720p|480p|4k|hd|hq|official|video|audio|song|lyrics|"
                  r"full|hdrip|webrip|remastered|remaster|320kbps|128kbps|64kbps)\b",
                  " ", text, flags=re.I)
    text = re.sub(r"^\s*\d{1,3}[\s.\-–]+", " ", text)          # leading track numbers
    return re.sub(r"\s+", " ", text).strip(" -–—.")


def _tagged(path: str) -> tuple[str, str] | None:
    """Real tags, if mutagen is present and the file actually carries them."""
    try:
        import mutagen  # type: ignore
    except Exception:
        return None
    try:
        audio = mutagen.File(path, easy=True)
        if not audio:
            return None
        artist = (audio.get("artist") or [""])[0]
        title = (audio.get("title") or [""])[0]
        if artist or title:
            return (str(artist), str(title))
    except Exception:
        return None
    return None


def _row(path: str, size: int, mtime: int) -> dict:
    ext = Path(path).suffix.lower()
    stem = _clean_name(Path(path).stem)
    artist = ""
    tags = _tagged(path) if ext in AUDIO_EXT else None
    if tags:
        artist, title = tags
        name = title or stem
    else:
        # No tags: keep the whole cleaned name. Guessing which side of "A - B" is the
        # artist is exactly the kind of invention that makes a music library untrustworthy.
        name = stem
    return {
        "path": path,
        "name": name or stem or Path(path).name,
        "artist": artist,
        "kind": "audio" if ext in AUDIO_EXT else "video",
        "ext": ext,
        "size": int(size),
        "mtime": int(mtime),
        "search": f"{name} {artist} {stem}".lower(),
    }


def scan(roots: str | list[str] = "", limit: int = MAX_FILES,
         include_drives: bool = True) -> dict:
    """Walk the roots and replace the index. Returns counts, never raises."""
    if isinstance(roots, str):
        chosen = [p.strip() for p in re.split(r"[|;,]", roots) if p.strip()]
    else:
        chosen = [str(p) for p in (roots or [])]
    asked_for = list(chosen)
    chosen = [os.path.expanduser(p) for p in chosen if os.path.isdir(os.path.expanduser(p))]
    if asked_for and not chosen:
        # The caller named a path that is not there (an unplugged disk). Do not fall
        # back to the default folders: that would silently replace a good index.
        return {"built": _CACHE.get("built", 0), "roots": asked_for,
                "tracks": _CACHE.get("tracks", []), "seconds": 0.0,
                "skipped": 0, "folders": 0,
                "error": f"nothing at {asked_for[0]} — is the disk plugged in?"}
    if not chosen:
        chosen = default_roots(include_drives=include_drives)

    started = time.time()
    tracks: list[dict] = []
    folders = 0
    skipped = 0
    seen_paths: set[str] = set()
    for root in chosen:
        base = Path(root)
        base_depth = len(base.parts)
        try:
            walker = os.walk(root, topdown=True, onerror=lambda _e: None)
            for dirpath, dirnames, filenames in walker:
                if len(Path(dirpath).parts) - base_depth >= MAX_DEPTH:
                    dirnames[:] = []
                dirnames[:] = [d for d in dirnames
                               if d.lower() not in SKIP_DIRS and not d.startswith(".")]
                folders += 1
                for name in filenames:
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in MEDIA_EXT:
                        continue
                    if len(tracks) >= limit:
                        break
                    full = os.path.join(dirpath, name)
                    if full in seen_paths:
                        continue
                    try:
                        stat = os.stat(full)
                    except OSError:
                        skipped += 1
                        continue
                    if stat.st_size < MIN_BYTES:    # thumbnails, cached art, stubs
                        skipped += 1
                        continue
                    seen_paths.add(full)
                    tracks.append(_row(full, stat.st_size, stat.st_mtime))
        except Exception:
            skipped += 1
            continue

    data = {"built": time.time(), "roots": chosen, "tracks": tracks,
            "seconds": round(time.time() - started, 2), "skipped": skipped,
            "folders": folders}
    try:
        path = _index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    except Exception:
        pass
    _CACHE.update({"built": data["built"], "tracks": tracks, "roots": chosen})
    return data


def load(force: bool = False) -> dict:
    """The index, from memory, then disk. Never rescans behind the user's back."""
    if (not force and _CACHE.get("tracks")
            and time.time() - _CACHE.get("built", 0) < CACHE_SECONDS):
        return _CACHE
    if not force:
        try:
            data = json.loads(_index_path().read_text(encoding="utf-8"))
            if data.get("tracks"):
                _CACHE.update(data)
                return _CACHE
        except Exception:
            pass
    return {"built": 0, "tracks": [], "roots": []}


# --------------------------------------------------------------------- search
def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())


def _tokens(text: str) -> list[str]:
    return [t for t in _norm(text).split() if len(t) > 1]


def _score(track: dict, query: str, tokens: list[str]) -> float:
    hay = track.get("search", "")
    name = _norm(track.get("name", ""))
    score = 0.0
    phrase = _norm(query).strip()
    if phrase and phrase in name:
        score += 60
        if name.startswith(phrase):
            score += 25
    elif phrase and phrase in hay:
        score += 40
    hit = sum(1 for token in tokens if token in hay)
    score += hit * 12
    if tokens and hit == len(tokens):
        score += 18
    if track.get("kind") == "video":
        score -= 2          # all else equal, a song request wants the song
    return score


def search(query: str = "", kind: str = "", limit: int = 8) -> list[dict]:
    """Rank tracks against a phrase. Empty query returns the most recent additions."""
    data = load()
    tracks = data.get("tracks") or []
    if kind in ("audio", "video"):
        tracks = [t for t in tracks if t.get("kind") == kind]
    query = (query or "").strip()
    if not query:
        return sorted(tracks, key=lambda t: -t.get("mtime", 0))[:limit]
    tokens = _tokens(query)
    if not tokens:
        return []
    scored = []
    for track in tracks:
        score = _score(track, query, tokens)
        # fuzzy last resort for typos and transliteration ("ilaiya nila" vs "ilaya nila")
        if score < 12 and len(query) >= 5:
            import difflib
            near = difflib.SequenceMatcher(None, _norm(query), _norm(track["name"])).ratio()
            if near > 0.72:
                score = max(score, near * 30)
        if score >= 12:
            scored.append((score, track))
    scored.sort(key=lambda row: (-row[0], row[1].get("mtime", 0)))
    return [t for _s, t in scored[:limit]]


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size / 1024:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def results_text(query: str = "", kind: str = "", limit: int = 8) -> str:
    data = load()
    tracks = data.get("tracks") or []
    if not tracks:
        return ("I have not indexed your music yet. Say **scan my music** or "
                "**scan my external disk** and I will look — read-only, nothing moved.")
    hits = search(query, kind, limit)
    where = f" for “{query}”" if query else ""
    if not hits:
        close = sorted(tracks, key=lambda t: -t.get("mtime", 0))[:3]
        sample = ", ".join(t["name"][:34] for t in close)
        return (f"No match{where} in {len(tracks)} indexed files. "
                f"Closest recent: {sample}. Try a shorter phrase, or rescan the folder "
                f"it lives in.")
    lines = [f"{len(hits)} match{'es' if len(hits) != 1 else ''}{where} "
             f"(index: {len(tracks)} files):"]
    for index, track in enumerate(hits, 1):
        artist = f" — {track['artist']}" if track.get("artist") else ""
        lines.append(f"  {index}. {track['name']}{artist}  [{track['kind']}, "
                     f"{_human_size(track['size'])}]  {track['path']}")
    return "\n".join(lines)


def stats() -> str:
    data = load()
    tracks = data.get("tracks") or []
    if not tracks:
        return ("No media indexed yet. Roots I would scan: "
                + ", ".join(default_roots()[:6]))
    audio = sum(1 for t in tracks if t.get("kind") == "audio")
    video = len(tracks) - audio
    total = sum(t.get("size", 0) for t in tracks)
    built = time.strftime("%d %b %H:%M", time.localtime(data.get("built", 0)))
    roots = ", ".join(data.get("roots") or [])
    return (f"{len(tracks)} media files · {audio} songs · {video} videos · "
            f"{total / 1e9:.1f} GB\n"
            f"indexed {built} from {roots}\n"
            f"scanned {len(data.get('roots') or [])} root(s); "
            f"playback never modifies a file")


def forget() -> str:
    _CACHE.update({"built": 0, "tracks": []})
    try:
        _index_path().unlink()
    except Exception:
        pass
    return "Media index cleared. Nothing on disk was touched — only my list of it."


def first_track(query: str = "", kind: str = "") -> dict | None:
    hits = search(query, kind, 1)
    return hits[0] if hits else None
