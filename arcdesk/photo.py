"""Real photographs — the honest answer to "no, I meant a *real* elephant".

`art.py` draws. A drawing is a drawing: clean vector shapes, correct at a glance,
nowhere near a photo. `generate.py` can make a photoreal image, but only when a
diffusion model is already running on the machine, and that wants 4-8 GB of VRAM.
Neither of those is a photo of a real elephant.

So this module does the third thing, which is free, needs no GPU, no key, no
account and no money: it finds a **real photograph that a human being took and
released under a free licence**, and it brings the credit along with it.

    search("african elephant")  ->  candidates with author, licence, source page
    fetch("african elephant")   ->  download the best one into the pictures folder
    report(photo)               ->  one line the model can read back to the user

Source is Wikimedia Commons (`commons.wikimedia.org`), queried over its public
API. No API key exists, so there is nothing to leak and nothing to pay for.

Three rules this file follows, because the whole point is not lying:

1. **It never claims a photo is generated.** Every result carries the file name,
   the photographer and the licence, and `report()` always prints them.
2. **It never silently swaps subjects.** If the search returns a "elephant seal"
   for "elephant", the title is shown so the person can see why.
3. **No network = a sentence, not an exception.** Offline it says so, and points
   at the offline alternatives (sketch, local diffusion).

Only freely-licensed works are kept: Commons hosts them, and the ones that are
public domain or CC-0 are preferred over CC BY-SA when both are present, because
a person reusing the picture later has less to think about.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = "ArcDesk/1.0 (free photo search; local app; +https://commons.wikimedia.org)"
TIMEOUT = 20.0
MAX_BYTES = 12 * 1024 * 1024          # a generous 12 MB ceiling per picture

# Licences that ask the least of whoever reuses the picture later.
EASIEST = ("cc0", "public domain", "pd", "no restrictions")

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _clean(value: str, limit: int = 120) -> str:
    """Commons metadata is HTML. Strip tags, collapse spaces, cut politely."""
    text = TAG_RE.sub(" ", str(value or ""))
    text = WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


# Commons "Artist" fields are often a paragraph: a name, then the file's whole
# provenance note. Cut at the first of these rather than printing all of it.
_ARTIST_CUTS = (" the making of", " this file", " this image", " own work",
                " facebook", " instagram", " twitter")


def _artist(value: str) -> str:
    text = _clean(value, 120)
    low = text.lower()
    for cut in _ARTIST_CUTS:
        i = low.find(cut)
        if i > 2:
            text = text[:i]
            break
    return _clean(text, 60) or "unknown photographer"


def _get(params: dict, api: str | None = None) -> dict:
    url = f"{api or API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _download(url: str, limit: int = MAX_BYTES) -> bytes:
    """Fetch raw bytes. Separate from `fetch()` so a test can run with no network."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read(limit + 1)


def search(query: str, limit: int = 6, api: str | None = None) -> list[dict]:
    """Free-licensed photographs matching `query`, best licence first.

    Returns [] for an empty query. Raises nothing for network trouble — the
    caller gets the reason from `fetch()`/`report()` instead, so a Lite intent
    can answer with a sentence.
    """
    q = (query or "").strip()
    if not q:
        return []
    data = _get({
        "action": "query", "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {q}",
        "gsrnamespace": 6,
        "gsrlimit": max(1, min(int(limit), 20)),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime",
        "iiurlwidth": 1600,
    }, api=api)

    pages = ((data.get("query") or {}).get("pages") or {})
    # generator=search returns an unordered dict; "index" holds the ranking
    ordered = sorted(pages.values(), key=lambda p: p.get("index", 9999))

    out: list[dict] = []
    for page in ordered:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        if info.get("mime") and not str(info["mime"]).startswith("image/"):
            continue
        url = info.get("thumburl") or info.get("url") or ""
        if not url:
            continue
        licence = _clean((meta.get("LicenseShortName") or {}).get("value", ""), 40)
        out.append({
            "title": _clean(page.get("title", ""), 90),
            "url": url,
            "page": info.get("descriptionurl", ""),
            "artist": _artist((meta.get("Artist") or {}).get("value", "")),
            "licence": licence or "unknown licence",
            "width": info.get("thumbwidth") or info.get("width") or 0,
            "height": info.get("thumbheight") or info.get("height") or 0,
            "bytes": info.get("size") or 0,
            "easy": any(k in licence.lower() for k in EASIEST),
        })

    # easiest licence first, then the original search order (sorted() is stable)
    out.sort(key=lambda p: 0 if p["easy"] else 1)
    return out


def pictures_dir() -> Path:
    """Where fetched photos land: Pictures/ArcPhotos, else the app data folder."""
    d = Path.home() / "Pictures" / "ArcPhotos"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:
        from . import config
        d = config.data_dir() / "photos"
        d.mkdir(parents=True, exist_ok=True)
        return d


def _safe_name(query: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", (query or "photo").strip())[:40].strip("_")
    return (stem or "photo").lower()


def _unique(target: Path) -> Path:
    """Never overwrite an earlier picture — same rule as the sketch saver."""
    if not target.exists():
        return target
    stem, i = target.stem, 2
    while True:
        cand = target.with_name(f"{stem}_v{i}{target.suffix}")
        if not cand.exists():
            return cand
        i += 1


def fetch(query: str, dest: str = "", limit: int = 6, api: str | None = None) -> dict:
    """Download the best free-licensed photograph of `query`.

    The returned dict always has `ok`. On success it also has `path`, `title`,
    `artist`, `licence`, `page`. On failure it has `error` — one plain sentence.
    """
    try:
        found = search(query, limit=limit, api=api)
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"no internet for photo search ({exc.reason})"}
    except Exception as exc:                                # noqa: BLE001
        return {"ok": False, "error": f"photo search failed: {type(exc).__name__}: {exc}"}

    if not found:
        return {"ok": False,
                "error": f"no free-licensed photograph found for '{query}' — try other words"}

    pick = found[0]
    ext = Path(urllib.parse.urlparse(pick["url"]).path).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"

    folder = Path(dest).expanduser() if dest else pictures_dir()
    if folder.suffix:                       # a file path was given, not a folder
        target = folder
        folder = target.parent
    else:
        target = folder / f"{_safe_name(query)}_{int(time.time())}{ext}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        target = _unique(target)
        blob = _download(pick["url"])
        if len(blob) > MAX_BYTES:
            return {"ok": False, "error": "the file is larger than the 12 MB limit"}
        # A JPEG/PNG/WebP/GIF header, or the download is refused: an error page
        # saved as "elephant.jpg" is exactly the kind of lie this file exists to avoid.
        if not (blob[:2] == b"\xff\xd8" or blob[:4] == b"\x89PNG" or blob[:4] == b"RIFF"
                or blob[:3] == b"GIF"):
            return {"ok": False, "error": "the download was not an image file"}
        target.write_bytes(blob)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"the picture could not be downloaded ({exc.code})"}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"no internet for the download ({exc.reason})"}
    except Exception as exc:                                # noqa: BLE001
        return {"ok": False, "error": f"could not save the picture: {type(exc).__name__}: {exc}"}

    return {"ok": True, "path": str(target), "title": pick["title"],
            "artist": pick["artist"] or "unknown photographer",
            "licence": pick["licence"], "page": pick["page"],
            "width": pick["width"], "height": pick["height"],
            "bytes": len(blob), "others": len(found) - 1}


def report(photo: dict, query: str = "") -> str:
    """One readable sentence (or two) that never hides where the picture came from."""
    if not photo.get("ok"):
        return (f"ERROR: {photo.get('error', 'no picture')}. "
                "Offline I can still draw a vector sketch, or you can run a local "
                "diffusion model for a generated image.")
    what = query or photo.get("title", "photo")
    line = (f"real photograph of {what}: {photo['path']} "
            f"({photo['width']}×{photo['height']}, {photo['bytes'] // 1024} KB) — "
            f"{photo['title']} by {photo['artist']}, {photo['licence']}. "
            f"Source: {photo['page']}")
    if photo.get("others"):
        line += f" {photo['others']} more candidates were found."
    return line


def describe() -> str:
    """What this module can do — used by the doctor/probe output."""
    return ("photo search: Wikimedia Commons (free licences, no key, no account); "
            f"pictures are saved to {pictures_dir()}")
