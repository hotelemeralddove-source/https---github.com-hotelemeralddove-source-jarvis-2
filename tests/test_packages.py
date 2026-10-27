"""The in-app catalogue tool — search, scan, plan, and the words that reach it.

What broke before this file existed: a substring search where "read" matched
"already", so "read a pdf" ranked a chat app above a PDF parser. Every check here
is a phrasing a real sentence produced.

Run:  python tests/test_packages.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk.ai import catalog, lite, packages, tools  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = (got == want) if not callable(want) else want(got)
    print(f"   {'OK  ' if good else 'FAIL'} {label:<48} {got!r}")
    ok &= bool(good)


print("1) search ranks the right project first")
for query, want in (("read a pdf", {"docling", "markitdown"}),
                    ("ocr a screenshot", {"tesseract", "paddleocr", "easyocr"}),
                    ("wake word", {"openwakeword", "sherpa-kws", "porcupine"}),
                    ("vector database", {"chroma", "qdrant", "faiss", "lancedb", "txtai"}),
                    ("convert a video to mp4", {"ffmpeg"})):
    top = {p.key for p in packages.search(query, limit=3)}
    check(query, bool(top & want), True)
    print(f"        → {[p.key for p in packages.search(query, limit=3)]}")

print("2) no substring traps")
# "read" must not match "already"; "see" must not match "seemingly" etc.
hits = [p.key for p in packages.search("read a pdf", limit=8)]
check("lmstudio out of a pdf query", "lmstudio" not in hits[:4])
check("mcp-servers out of a pdf query", "mcp-servers" not in hits[:3])

print("3) every formatter returns text, never raises")
for name, text in (("list", packages.list_text("ocr")),
                   ("empty list", packages.list_text("zzzznothing")),
                   ("bad role", packages.list_text("", "nonsense")),
                   ("scan", packages.scan_text("ears")),
                   ("plan", packages.plan_text("mouth")),
                   ("summary", packages.summary_text()),
                   ("detail", packages.detail("sherpa")),
                   ("detail miss", packages.detail("nope")),
                   ("refused", packages.refused_text())):
    check(name, isinstance(text, str) and len(text) > 10)

print("4) the tool is registered and answers every action")
check("packages in TOOLS", "packages" in tools.TOOLS)
for action in ("search", "scan", "plan", "all", "detail"):
    out = tools.call("packages", {"action": action, "query": "ocr", "key": "sherpa"})
    check(f"action={action}", isinstance(out, str) and "ERROR" not in out[:12])

print("5) the phrases that reach it")
for phrase, action in (("which open source package can read a pdf", "search"),
                       ("scan my github stack", "scan"),
                       ("what is missing in ears", "plan"),
                       ("how many packages are catalogued", "all")):
    _, calls = lite.respond(phrase)
    got = calls[0]["function"]["arguments"] if calls else ""
    check(phrase, action in got, True)

print("6) and the phrases that must not")
for phrase in ("can you see my screen", "what is missing on my screen",
               "show me the hologram", "remind me in 5 minutes to call amma"):
    _, calls = lite.respond(phrase)
    name = calls[0]["function"]["name"] if calls else ""
    check(phrase, name != "packages", True)

print("7) counts agree with the data")
check("summary mentions the real total",
      str(len(catalog.CATALOG)) in packages.summary_text())
check("wired count", packages.summary_text().count("wired") >= 1)

print("\nPASS" if ok else "\nFAIL")
raise SystemExit(0 if ok else 1)
