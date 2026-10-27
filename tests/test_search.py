"""File search — the index must stay read-only, bounded, and honest about misses.

The rule the user set is simple and non-negotiable: **never damage my files**.
So this test proves three things: nothing is ever written outside the app's own
data folder, a walk cannot run away, and a miss says so instead of guessing.

Run:  python tests/test_search.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="arcdesk-user-")
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ["ARCDESK_USER_HOME"] = HOME          # never touch the real profile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import search  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<50} {got!r}")
    ok &= bool(good)


# a tiny fake home, so the test knows exactly what should be found
home = Path(HOME)
(home / "Documents" / "invoices").mkdir(parents=True)
(home / "Downloads").mkdir()
(home / "Documents" / "invoices" / "march-invoice.pdf").write_text("pdf-ish", encoding='utf-8')
(home / "Downloads" / "holiday-photo.jpg").write_text("jpg-ish", encoding='utf-8')
(home / "Documents" / "notes.txt").write_text(
    "the arc reactor needs a new coolant loop\nsecond line\n", encoding='utf-8')

print("1) the index knows what is in the folders")
before = set(str(p) for p in home.rglob("*"))
data = search.refresh(force=True)
check("refresh returns a dict", isinstance(data, dict), True)
check("files indexed", len(data.get("files", [])) >= 3, True)
after = set(str(p) for p in home.rglob("*"))
check("nothing created or deleted in the user's folders", after, before)

print("2) search finds by name, ignoring case")
text = search.find("invoice")
check("invoice found", "march-invoice" in text, True)
check("case does not matter", "march-invoice" in search.find("INVOICE"), True)
check("a miss says nothing matched", "nothing matching" in search.find("zzz").lower(), True)

print("3) type filters narrow, they do not lie")
check("pdf filter keeps the pdf",
      "march-invoice" in search.find("invoice", kind="pdf"), True)
check("image filter keeps the image",
      "holiday-photo" in search.find("holiday", kind="image"), True)
check("a pdf is not a video",
      "nothing matching" in search.find("invoice", kind="video").lower(), True)

print("4) grep reads inside text files, read-only")
grep = search.find("coolant", grep=True)
check("grep found the line", "notes.txt" in grep, True)
check("file is unchanged",
      "coolant" in (home / "Documents" / "notes.txt").read_text(encoding="utf-8"), True)

print("5) a miss is a miss")
check("nonsense finds nothing",
      "nothing matching" in search.find("zzzzznothing").lower(), True)

print("6) the walk is bounded and quick")
t0 = time.time()
search.refresh(force=True)
spent = time.time() - t0
check("index of a tiny home is fast", spent < 5.0, True)
check("file cap is sane", search.MAX_FILES >= 1000, True)
check("depth cap is sane", 1 <= search.MAX_DEPTH <= 12, True)
check("skip list covers noise", any(d in search.SKIP_DIRS
                                    for d in ("node_modules", ".git")), True)

print("7) stats reports real numbers")
stats = search.stats()
check("stats is text", isinstance(stats, str) and len(stats) > 10, True)
check("stats names the count", any(ch.isdigit() for ch in stats), True)

print("\nPASS" if ok else "\nFAIL")
raise SystemExit(0 if ok else 1)
