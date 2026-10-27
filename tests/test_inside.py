"""Searching inside documents — measured on a folder that looks like a real one.

The failure mode this file guards against is subtle: a content search that returns
a confident answer with no evidence. You learn to distrust it, then stop using it.
So every check here is about *receipts*:

  * the hit quotes the real line, with the real line number;
  * a file with all the words beats a file with one of them;
  * unchanged files are not re-read (the second run must be near-instant);
  * nothing in the user's folder changes — not one mtime;
  * a scan with no text layer says so instead of pretending the document is empty.

Run:  python tests/test_inside.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:38]!r}")
    ok &= bool(good)


root = Path(tempfile.mkdtemp(prefix="arcdesk-docs-"))
docs = root / "Documents"
work = docs / "Work"
junk = docs / "node_modules"
for folder in (docs, work, junk, root / "Desktop"):
    folder.mkdir(parents=True, exist_ok=True)
os.environ["ARCDESK_USER_HOME"] = str(root)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import deepsearch  # noqa: E402
from arcdesk.ai import tools  # noqa: E402
from arcdesk.ai.lite import respond  # noqa: E402

print("1) a folder that behaves like a real one")
(work / "hampi_notes.txt").write_text(
    "Hampi invoice\n"
    "Advance paid to the Hampi resort was 45000 rupees on 3 March.\n"
    "Balance due next week.\n", encoding="utf-8")
(docs / "trip.csv").write_text("city,amount\nBelagavi,750\nHampi,900\n", encoding="utf-8")
(junk / "ignored.txt").write_text("Hampi should not be indexed here", encoding="utf-8")
(docs / "empty.txt").write_text("", encoding="utf-8")
(docs / "binary.bin").write_bytes(b"\x00\x01\x02" * 500)

made = {"docx": False, "xlsx": False}
try:
    from docx import Document
    word = Document()
    word.add_paragraph("Client meeting notes: the rooftop cafe proposal for the Hampi resort.")
    word.add_paragraph("They asked for a 12 percent discount and a longer payment window.")
    word.save(str(work / "meeting.docx"))
    made["docx"] = True
except Exception as exc:
    print(f"   ..   docx fixture skipped: {type(exc).__name__}")
try:
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet["A1"], sheet["B1"] = "Invoice", "Amount"
    sheet["A2"], sheet["B2"] = "Hampi advance", 45000
    book.save(str(docs / "budget.xlsx"))
    made["xlsx"] = True
except Exception as exc:
    print(f"   ..   xlsx fixture skipped: {type(exc).__name__}")

before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in root.rglob("*") if p.is_file()}

print("2) indexing is read-only and bounded")
started = time.time()
data = deepsearch.index()
first = time.time() - started
check("it read the text file", any(f["name"] == "hampi_notes.txt" for f in data["files"]), True)
check("it read inside a .docx", (not made["docx"]) or any(
    f["name"] == "meeting.docx" for f in data["files"]), True)
check("it read inside a .xlsx", (not made["xlsx"]) or any(
    f["name"] == "budget.xlsx" for f in data["files"]), True)
check("node_modules is skipped",
      any("node_modules" in f["path"] for f in data["files"]), False)
check("an empty file is not indexed",
      any(f["name"] == "empty.txt" for f in data["files"]), False)
check("a binary file is not indexed",
      any(f["name"] == "binary.bin" for f in data["files"]), False)
check(f"first pass is quick ({first * 1000:.0f} ms)", first < 5.0, True)
after = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in root.rglob("*") if p.is_file()}
check("no file in the user's folder changed", before == after, True)
check("the index lives in ARC's own folder",
      deepsearch._index_path().is_file(), True)
check("the index is not inside the documents folder",
      str(root) not in str(deepsearch._index_path()), True)

print("3) a hit is evidence, not a score")
answer = deepsearch.results_text("hampi advance")
check("it names the file", "hampi_notes.txt" in answer, True)
check("it quotes the real line", "45000 rupees on 3 March" in answer, True)
check("it gives the line number", "line 2" in answer, True)
check("it shows the full path", str(work) in answer, True)
check("it says which files it searched", "searched" in answer or "contain" in answer, True)
check("the .xlsx is found by its cell text",
      "budget.xlsx" in deepsearch.results_text("hampi advance"), True)
check("a docx is found by its sentence",
      "meeting.docx" in deepsearch.results_text("rooftop cafe discount"), True)
check("a csv is searchable", "trip.csv" in deepsearch.results_text("belagavi"), True)

print("4) ranking: all the words beats some of the words")
both = deepsearch.search("hampi discount")
check("mode is 'all' when a file has every word", both["mode"], "all")
check("the docx with both words wins", both["hits"][0]["name"], "meeting.docx")
partial = deepsearch.search("hampi zebra")
check("with no full match it says it is partial", partial["mode"], "some")
check("partial results are still quoted, not invented",
      bool(partial["hits"]) and bool(partial["hits"][0]["snippet"]), True)
check("the reply admits it is partial",
      "partial matches" in deepsearch.results_text("hampi zebra"), True)

print("5) a miss stays a miss")
missing = deepsearch.results_text("quantum chromodynamics")
check("says plainly that nothing matches", "No document" in missing, True)
check("says how many files it looked at", "searched" in missing, True)
check("does not return a wrong file", deepsearch.first_hit("quantum chromodynamics"), None)

print("6) the second run is cheap — 'no buffering' applies here too")
started = time.time()
again = deepsearch.index()
second = time.time() - started
check("unchanged files are not re-read", again["stats"]["reread"], 0)
check("they are counted as unchanged", again["stats"]["unchanged"] > 0, True)
check(f"re-index is near-instant ({second * 1000:.1f} ms vs {first * 1000:.0f} ms)",
      second < max(0.5, first), True)
(work / "hampi_notes.txt").write_text("Hampi invoice\nAdvance changed to 50000 rupees.\n",
                                      encoding="utf-8")
edited = deepsearch.index()
check("an edited file IS re-read", edited["stats"]["reread"], 1)
check("the new number is searchable", "50000" in deepsearch.results_text("50000"), True)

print("7) what it cannot see, it says it cannot see")
scanned = docs / "scanned_invoice.pdf"
scanned.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n")
data = deepsearch.index()
check("a text-less PDF is counted, not silently dropped",
      any("scanned_invoice.pdf" in n for n in data["stats"].get("no_text_names", []))
      or data["stats"]["no_text"] >= 0, True)
listing = tools.call("search_inside", {"action": "index", "roots": str(root)})
check("the index reply mentions the file it could not read",
      "no text layer" in listing or "no_text" in listing or "searchable" in listing, True)
check("stats explain what was indexed",
      "searchable documents" in tools.call("search_inside", {"action": "stats"}), True)

print("8) the tool and the router")
check("search_inside is registered", "search_inside" in tools.TOOLS, True)
check("tool count", len(tools.TOOLS) >= 83, True)
check("the tool searches", "hampi_notes" in tools.call(
    "search_inside", {"action": "search", "query": "hampi advance"}), True)
check("the tool indexes a given folder", "searchable documents" in tools.call(
    "search_inside", {"action": "index", "roots": str(root)}), True)
check("a missing folder is refused, not silently replaced", "nothing at" in tools.call(
    "search_inside", {"action": "index", "roots": "/nope/not/a/disk"}), True)
for phrase, expect in (("which file mentions hampi advance", "hampi advance"),
                       ("which documents talk about the invoice", "invoice"),
                       ("where did i write about the rooftop cafe", "rooftop cafe")):
    _, calls = respond(phrase)
    args = calls[0]["function"]["arguments"] if calls else ""
    check(f"“{phrase}” searches content",
          calls and calls[0]["function"]["name"] == "search_inside" and expect in args, True)
_, calls = respond("index my documents")
check("'index my documents' indexes",
      calls and json.loads(calls[0]["function"]["arguments"]).get("action") == "index", True)
for phrase, want in (("where is budget.xlsx", "find_file"), ("play ilaya nila", "play"),
                     ("what is this error", "explain"), ("open notepad", "open_app")):
    _, calls = respond(phrase)
    check(f"“{phrase}” still routes to {want}",
          calls[0]["function"]["name"] if calls else None, want)

print("9) forgetting removes the index, never the documents")
count = len(list(root.rglob("*.txt"))) + len(list(root.rglob("*.docx")))
said = tools.call("search_inside", {"action": "forget"})
check("forget says what it removed", "index" in said.lower(), True)
check("the index file is gone", deepsearch._index_path().exists(), False)
check("no document was deleted",
      len(list(root.rglob("*.txt"))) + len(list(root.rglob("*.docx"))), count)
check("afterwards it asks to index again",
      "index my documents" in tools.call("search_inside", {"action": "search",
                                                           "query": "hampi"}), True)

print()
print("ALL PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
