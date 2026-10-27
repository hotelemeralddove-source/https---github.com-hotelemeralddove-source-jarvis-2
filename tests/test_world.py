"""The library: "ARC knows everything", made honest.

The claim only survives if four rules hold, and each one is a test here:

1. Nothing is in the shelf without a source and a date.
2. Anything that drifts (population, CO2, repo rate, GST slabs) is always quoted
   with its year, never as "today".
3. A question the library cannot answer comes back as "I do not know" *plus* a
   real source link — never a confident sentence.
4. Your own files count as knowledge: once indexed, ARC quotes the filename.

Run:  python tests/test_world.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import world  # noqa: E402
from arcdesk.ai import tools  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<54} {str(got)[:44]!r}")
    ok &= bool(good)


print("1) every entry is sourced and dated")
bad_source = [e[0] for e in world.ENTRIES if not str(e[4]).strip()]
bad_date = [e[0] for e in world.ENTRIES
            if not (isinstance(e[5], int) and 1900 < e[5] <= 2026)]
check("no entry without a source", bad_source, [])
check("no entry without a sane year", bad_date, [])
check("every entry has at least one question form",
      [e[0] for e in world.ENTRIES if not e[2]], [])
check("ids are unique", len({e[0] for e in world.ENTRIES}), len(world.ENTRIES))
check("all domains are declared",
      [e[1] for e in world.ENTRIES if e[1] not in world.DOMAINS], [])

print("2) a drifting number is never stated without its year")
moves = [e for e in world.ENTRIES if e[6]]
check("there are entries flagged as moving", len(moves) > 0, True)
for entry in moves:
    ident, _domain, forms, _answer, _source, year, _moves = entry
    # the year travels with the citation, so the *answer the user sees* carries it
    shown = world.ask(forms[0])
    check(f"{ident}: answer shows {year}", str(year) in shown, True)
    check(f"  · {ident} is not stated as live", "right now" not in shown.lower(), True)

print("3) known questions get a cited answer")
everest = world.ask("how tall is everest")
check("everest height", "8,848" in everest, True)
check("everest cites a source", "source:" in everest.lower(), True)
states = world.ask("how many states in india")
check("states = 28 + 8", "28 states" in states and "8 union territories" in states, True)
quiz = world.ask("what is a qubit")
check("qubit answered from disk", "I do not know" not in quiz, True)
check("a one-word question still clears the bar",
      "30 chest compressions" in world.ask("what is cpr"), True)
check("an apostrophe does not break matching",
      "1.43 billion" in world.ask("what is india's population"), True)
check("but a vague single word is still refused",
      "do not know" in world.ask("what is life").lower(), True)

print("4) a live question is refused, not guessed")
for question in ("who won the 2024 election", "gold price today",
                 "who is the chief minister of karnataka now"):
    answer = world.ask(question)
    check(f"refuses {question[:26]!r}", "do not know" in answer.lower(), True)
    check("  · and offers a real link", "http" in answer, True)
china = world.ask("what is the population of china right now")
check("a drifting number is answered *with its year*",
      "1.43 billion" in china and "2024" in china, True)
check("and it says the number changes", "changes" in china, True)
check("unknown() names no fact", "do not have a live news feed" in world.unknown().lower()
      or "will not improvise" in world.unknown().lower(), True)

print("5) coverage() counts what is actually there")
cov = world.coverage()
check("total matches the shelf", str(len(world.ENTRIES)) in cov, True)
for name in world.DOMAINS:
    count = sum(1 for e in world.ENTRIES if e[1] == name)
    check(f"  {name}", str(count) in cov, True)
check("counts add up",
      sum(1 for e in world.ENTRIES if e[1] in world.DOMAINS), len(world.ENTRIES))
check("unknown domain is a sentence, not a crash",
      "No domain called" in world.domain("astrology"), True)
check("random_fact returns a cited line", "source:" in world.random_fact().lower(), True)

print("6) your own files become knowledge")
shelf = Path(tempfile.mkdtemp(prefix="arcdesk-lib-"))
(shelf / "neeli.md").write_text(
    "Neeli is our rooftop cafe. It opens in November with twelve rooms. "
    "Breakfast is included for direct bookings only.", encoding="utf-8")
(shelf / "ignore.bin").write_bytes(b"\x00\x01\x02")
report = world.ingest(str(shelf))
check("ingest reports the file", "Indexed 1 file(s)" in report, True)
own = world.ask("what is the rooftop cafe called")
check("answer comes from my file", "neeli.md" in own, True)
check("quotes, does not paraphrase", "Quoted, not paraphrased" in own, True)
check("the quote comes from the file, not from a guess",
      "Neeli is our rooftop cafe" in own, True)

print("7) a real lookup cites its date, and fails honestly offline")
fake = {"title": "Vikram Sarabhai", "extract": "Vikram Sarabhai was an Indian physicist.",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Vikram_Sarabhai"}}}
with mock.patch("urllib.request.urlopen") as opener:
    opener.return_value.__enter__.return_value.read.return_value = (
        b'{"title":"Vikram Sarabhai","extract":"Vikram Sarabhai was an Indian physicist.'
        b' He founded ISRO.","content_urls":{"desktop":{"page":'
        b'"https://en.wikipedia.org/wiki/Vikram_Sarabhai"}}}')
    live = world.fetch("Vikram Sarabhai")
check("returns the summary", "Indian physicist" in live, True)
check("cites the url", "wikipedia.org/wiki/Vikram_Sarabhai" in live, True)
check("stamps the date", "read just now" in live, True)
check("unused fixture matches", fake["title"] in live, True)

world.library_dir().joinpath("wiki_cache.json").unlink(missing_ok=True)
with mock.patch("urllib.request.urlopen", side_effect=OSError("no route")):
    offline = world.fetch("Some Topic Nobody Cached")
check("offline says so", "could not reach the source" in offline, True)
check("offline refuses to improvise", "will not answer from memory" in offline, True)

print("8) it is wired as a tool and never raises")
check("facts is registered", "facts" in tools.TOOLS, True)
check("tool count", len(tools.TOOLS) >= 74, True)
via_tool = tools.call("facts", {"action": "ask", "question": "how tall is everest"})
check("tool returns the library answer", "8,848" in via_tool, True)
check("coverage action", "sourced facts" in tools.call("facts", {"action": "coverage"}), True)
check("domain action", "TECH" in tools.call("facts", {"action": "domain", "domain": "tech"}),
      True)
check("fetch with no topic asks back", "What should I look up" in
      tools.call("facts", {"action": "fetch", "topic": ""}), True)

print()
print("ALL PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
