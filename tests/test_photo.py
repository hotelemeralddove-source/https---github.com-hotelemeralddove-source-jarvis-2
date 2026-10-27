"""Real photographs, or an honest refusal — never a drawing passed off as a photo.

The complaint this answers, in the user's words: "nethu elephant draw pannuchu,
real elephant picture-oda evlo different... apadiyae irukanum, realistic ah".

A vector sketch cannot become a photograph, so the fix is not "draw better": it is
to fetch a **real photograph, freely licensed**, and say where it came from. That
means this file has to prove the unglamorous things:

  * the Commons JSON is parsed correctly (title, photographer, licence, size);
  * easily-reusable licences (CC0 / public domain) are preferred, not scraper order;
  * a download that is not actually an image is refused, not saved as .jpg;
  * an earlier picture with the same name is never overwritten;
  * offline is a sentence, not a traceback;
  * the reply ALWAYS names the photographer and the licence — the whole point;
  * Lite routes "real photo of an elephant" here, and leaves "make an image of a
    dog" with the generator, and knows "aane" means elephant;
  * the cost of a lookup is a network call, so it is never run on every keystroke.

No network is used: `photo._get` and `photo._download` are replaced with fakes.

Run:  python tests/test_photo.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import urllib.error
from pathlib import Path

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-photo-home-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import art, photo  # noqa: E402
from arcdesk.ai import lite, tools  # noqa: E402

ok = True
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 400
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 400


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:34]!r}")
    ok &= bool(good)


def commons(item: dict) -> dict:
    """One page of a real Commons `generator=search` reply, shaped as the API does."""
    meta = {
        "LicenseShortName": {"value": item.get("licence", "")},
        "Artist": {"value": item.get("artist", "")},
    }
    info = {
        "thumburl": item.get("url", "https://upload.wikimedia.org/x.jpg"),
        "url": item.get("url", "https://upload.wikimedia.org/x.jpg"),
        "descriptionurl": item.get("page", "https://commons.wikimedia.org/wiki/File:x.jpg"),
        "thumbwidth": item.get("w", 1600), "thumbheight": item.get("h", 1067),
        "size": item.get("bytes", 900_000), "mime": item.get("mime", "image/jpeg"),
        "extmetadata": meta,
    }
    return {"title": item["title"], "index": item.get("index", 1), "imageinfo": [info]}


real_search = photo.search


def fake_api(pages: list[dict]):
    def _get(params, api=None):
        return {"query": {"pages": {str(i): commons(p) for i, p in enumerate(pages)}}}
    return _get


print("\n1) Commons JSON -> candidates")
photo._get = fake_api([
    {"title": "File:African Bush Elephant.jpg", "index": 1, "licence": "GFDL 1.2",
     "artist": '<a href="/wiki/User:Muhammad">Muhammad Mahdi Karim</a>', "w": 1600, "h": 2400},
    {"title": "File:Desert elephant spraying sand.jpg", "index": 2, "licence": "CC BY-SA 4.0",
     "artist": "<bdi><a href='#'>Charles J. Sharp</a></bdi>", "w": 1600, "h": 1067},
    {"title": "File:Elephant seal pup.jpg", "index": 3, "licence": "CC0",
     "artist": "Jane Doe", "w": 1200, "h": 800},
])
found = photo.search("elephant", limit=3)
check("3 candidates parsed", len(found), 3)
sharp = next(p for p in found if "Desert" in p["title"])
check("HTML stripped from the photographer", sharp["artist"], "Charles J. Sharp")
check("CC0 sorted ahead of CC BY-SA", found.index(found[0]) < found.index(sharp), True)
check("easiest licence first", found[0]["title"], "File:Elephant seal pup.jpg")
check("CC0 recognised as easy", found[0]["easy"])
check("GFDL is not 'easy'", any(p["easy"] for p in found if "Bush" in p["title"]), False)
check("source page kept", found[0]["page"].startswith("https://commons.wikimedia.org/"))
check("empty query asks nothing of the network", photo.search("   "), [])
check("seal is not silently renamed", "seal" in found[0]["title"])

print("\n2) a non-image is refused, not saved as .jpg")
photo.search = lambda q, limit=6, api=None: [{
    "title": "File:not-an-image.jpg", "url": "https://example.invalid/n.jpg",
    "page": "", "artist": "x", "licence": "CC0", "width": 1, "height": 1,
    "bytes": 10, "easy": True}]
photo._download = lambda url, limit=photo.MAX_BYTES: b"<html>404</html>"
got = photo.fetch("elephant", dest=tempfile.mkdtemp())
check("refused", got["ok"], False)
check("reason is plain language", "not an image" in got["error"], True)

print("\n3) a real picture is saved, named, and never overwrites")
folder = Path(tempfile.mkdtemp())
photo._download = lambda url, limit=photo.MAX_BYTES: JPEG
first = photo.fetch("african elephant", dest=str(folder))
check("saved", first["ok"])
check("file exists", Path(first["path"]).exists())
check("bytes match", Path(first["path"]).stat().st_size, len(JPEG))
check("name is derived from the ask", Path(first["path"]).name.startswith("african_elephant"))
second = photo.fetch("african elephant", dest=str(folder))
check("second copy is a new file", Path(second["path"]).name != Path(first["path"]).name)
check("first file still there", Path(first["path"]).exists())
check("both files present", len(list(folder.glob("*.jpg"))), 2)

print("\n4) the reply names the photographer and the licence, always")
line = photo.report(first, "african elephant")
check("says it is a real photograph", "real photograph of african elephant" in line, True)
check("names the file", "not-an-image" in line, True)
check("credits the photographer", "by x" in line, True)
check("states the licence", "CC0" in line, True)
check("links the source page", "Source:" in line, True)
check("path is in the reply", first["path"] in line, True)

print("\n5) no result and no network are sentences, not tracebacks")
photo.search = lambda q, limit=6, api=None: []
nothing = photo.fetch("a colour nobody photographed")
check("no result tolerated", nothing["ok"], False)
check("suggests other words", "other words" in nothing["error"], True)
check("report explains the failure", photo.report(nothing).startswith("ERROR:"), True)


def _offline(*a, **k):
    raise urllib.error.URLError("no route to host")


photo.search = real_search              # real search(), but the network refuses
photo._get = _offline
offline = photo.fetch("elephant")
check("offline is an error dict", offline["ok"], False)
check("offline message is honest", "no internet" in offline["error"], True)
check("offline report offers the sketch", "sketch" in photo.report(offline), True)

print("\n6) Lite sends 'real photo' here and leaves drawing alone")
check("real photo of an elephant", lite._photo_subject("real photo of an elephant"), "elephant")
check("show me a real elephant photo", lite._photo_subject("show me a real elephant photo"),
      "elephant")
check("picture of a tiger", lite._photo_subject("picture of a tiger"), "tiger")
check("make me an image of a dog stays a generation", lite._photo_subject("make me an image of a dog"), "")
check("draw an elephant stays a drawing", lite._photo_subject("draw an elephant"), "")
check("bare word 'picture' is not a subject", lite._photo_subject("picture"), "")
check("Tamil alias routed", lite._photo_subject("aane photo"), "aane")
check("alias maps to the English word", art.ALIAS.get("aane"), "elephant")

print("\n7) the registry knows the tool, and it is not a confirm-to-run action")
check("photo is registered", "photo" in tools.TOOLS)
check("photo needs a query", tools.TOOLS["photo"].required, ("query",))
check("photo never asks for confirmation", tools.TOOLS["photo"].confirm, False)
check("description says 'real photograph'",
      "real photograph" in tools.TOOLS["photo"].description, True)

print("\n" + ("ALL PASS" if ok else "SOMETHING FAILED"))
sys.exit(0 if ok else 1)
