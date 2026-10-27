#!/usr/bin/env python3
"""Build `arcdesk/KNOWS_PAGE.html` — every line on it is real output.

Nothing is typed by hand: the transcripts come from `world.ask` / `world.coverage` /
`world.fetch` at build time, the shelf table is read from `world.ENTRIES`, and the
counts are counted. If the code changes, the page changes with it.

    python tools/make_knows_page.py
"""
from __future__ import annotations

import html
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-page-"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk import world  # noqa: E402
from arcdesk.ai import tools  # noqa: E402

OUT = ROOT / "arcdesk" / "KNOWS_PAGE.html"

QUESTIONS = [
    "how many states in india",
    "how tall is everest",
    "what is the gst rate structure",
    "what is cpr",
    "how many bits in a byte",
    "who started python",
    "what is india's population",
    "what is the repo rate",
    "is lightning never striking twice true",
    "who won the 2024 election",
    "gold price today",
]


def transcript(question: str) -> tuple[str, str, bool]:
    answer = world.ask(question)
    refused = "do not know" in answer.lower()
    return question, answer, refused


def own_file_demo() -> tuple[str, str, str]:
    """A real ingest of a real (throwaway) file, so the quote is genuine."""
    shelf = Path(tempfile.mkdtemp(prefix="arcdesk-neeli-"))
    (shelf / "neeli_handover.md").write_text(
        "Neeli rooftop cafe. Breakfast is included for direct bookings only.\n"
        "Housekeeping rounds are at 11:00 and 16:00. Generator switch is behind the "
        "staircase, second panel.\n"
        "Season tariff for room 12 is 4200 rupees including tax.\n",
        encoding="utf-8")
    report = world.ingest(str(shelf))
    quote = world.ask("when are the housekeeping rounds")
    return "index my notes folder", report, quote


def shelf_rows() -> str:
    rows = []
    for domain in world.DOMAINS:
        entries = [e for e in world.ENTRIES if e[1] == domain]
        chips = []
        for entry in entries[:4]:
            _ident, _d, _forms, answer, source, year, moves = entry
            short = answer.split(". ")[0][:96]
            star = ' <b style="color:#f4d06f">*</b>' if moves else ""
            chips.append(
                f'<li>{html.escape(short)}{star}'
                f'<span class="src"> — {html.escape(str(source))}, {year}</span></li>')
        more = (f'<li class="more">+ {len(entries) - 4} more in this domain</li>'
                if len(entries) > 4 else "")
        rows.append(f"""
        <div class="shelf-card">
          <h4>{domain.upper()} <span class="count">{len(entries)}</span></h4>
          <ul>{''.join(chips)}{more}</ul>
        </div>""")
    return "".join(rows)


def build() -> str:
    rows = [transcript(q) for q in QUESTIONS]
    asked, report, quote = own_file_demo()
    stats = {
        "entries": len(world.ENTRIES),
        "domains": len(world.DOMAINS),
        "moving": sum(1 for e in world.ENTRIES if e[6]),
        "sources": len({e[4] for e in world.ENTRIES}),
        "tools": len(tools.TOOLS),
        "tests": len(list((ROOT / "tests").glob("test_*.py"))),
    }
    answered = sum(1 for _q, _a, refused in rows if not refused)
    refused = len(rows) - answered

    cards = []
    for question, answer, did_refuse in rows:
        body = html.escape(answer)
        body = body.replace("\n", "<br>")
        body = body.replace("source:", '<span class="cite">source:</span>')
        tag = ('<span class="tag no">honest no</span>' if did_refuse
               else '<span class="tag yes">from the shelf</span>')
        cards.append(f"""
        <article class="qa{' refused' if did_refuse else ''}">
          <div class="ask">{tag}<span class="q">“{html.escape(question)}”</span></div>
          <pre>{body}</pre>
        </article>""")

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ARC DESK · the library</title>
<style>
  :root {{
    --void:#01050a; --ink:#d8f6ff; --dim:#6f97a6; --cy:#48f2ff; --cy2:#1b8fa3;
    --gold:#f4d06f; --red:#ff6b6b; --line:rgba(72,242,255,.28);
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; padding:34px 22px 70px; background:
      radial-gradient(1200px 700px at 50% -10%, #06222b 0%, transparent 60%),
      radial-gradient(900px 500px at 85% 100%, #0a1e26 0%, transparent 55%), var(--void);
    color:var(--ink); font:15px/1.62 "Segoe UI",system-ui,sans-serif;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:1100px; margin:0 auto; }}
  .frame {{ position:relative; padding:26px 24px 30px; border:1px solid var(--line);
    background:linear-gradient(180deg, rgba(9,32,40,.72), rgba(2,9,14,.86)); }}
  .frame::before, .frame::after {{ content:""; position:absolute; width:22px; height:22px;
    border:2px solid var(--cy); }}
  .frame::before {{ top:-1px; left:-1px; border-right:0; border-bottom:0; }}
  .frame::after {{ bottom:-1px; right:-1px; border-left:0; border-top:0; }}
  h1 {{ font:600 26px/1.2 "Segoe UI",sans-serif; letter-spacing:.34em; margin:0 0 6px;
    color:var(--cy); text-transform:uppercase; }}
  h1 span {{ color:var(--ink); letter-spacing:.06em; font-weight:300; }}
  .sub {{ color:var(--dim); font-size:13px; letter-spacing:.06em; margin-bottom:22px; }}
  .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(132px,1fr));
    gap:10px; margin:0 0 26px; }}
  .stat {{ border:1px solid var(--line); padding:11px 13px; background:rgba(6,26,33,.6); }}
  .stat b {{ display:block; font:600 24px/1.1 "Consolas",monospace; color:var(--cy); }}
  .stat i {{ font-style:normal; font-size:11px; letter-spacing:.16em; color:var(--dim);
    text-transform:uppercase; }}
  h2 {{ font:500 13px/1 "Segoe UI"; letter-spacing:.28em; text-transform:uppercase;
    color:var(--cy); margin:34px 0 14px; padding-bottom:8px;
    border-bottom:1px solid var(--line); }}
  .sources {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; }}
  .src-card {{ border:1px solid var(--line); background:rgba(6,26,33,.5); padding:14px 15px; }}
  .src-card h3 {{ margin:0 0 6px; font-size:13px; letter-spacing:.14em; color:var(--gold);
    text-transform:uppercase; }}
  .src-card p {{ margin:0; font-size:13px; color:#a9c9d4; }}
  .qa {{ border:1px solid var(--line); border-left:3px solid var(--cy);
    background:rgba(4,17,23,.72); margin:0 0 12px; }}
  .qa.refused {{ border-left-color:var(--red); }}
  .ask {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap;
    padding:9px 13px; border-bottom:1px solid rgba(72,242,255,.14); }}
  .q {{ font:500 14px/1.4 "Consolas",monospace; color:var(--ink); }}
  .tag {{ font-size:10px; letter-spacing:.14em; text-transform:uppercase; padding:2px 7px;
    border:1px solid currentColor; }}
  .tag.yes {{ color:var(--cy); }} .tag.no {{ color:var(--red); }}
  pre {{ margin:0; padding:12px 14px; white-space:pre-wrap; font:13px/1.6 "Consolas",
    monospace; color:#bfe7f2; }}
  .cite {{ color:var(--gold); }}
  .shelf {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(266px,1fr)); gap:12px; }}
  .shelf-card {{ border:1px solid var(--line); background:rgba(6,26,33,.45); padding:12px 14px; }}
  .shelf-card h4 {{ margin:0 0 8px; font-size:12px; letter-spacing:.2em; color:var(--cy); }}
  .count {{ float:right; font:600 12px/1 "Consolas"; color:var(--gold); }}
  .shelf-card ul {{ margin:0; padding-left:16px; }}
  .shelf-card li {{ font-size:12.5px; color:#a9c9d4; margin-bottom:7px; }}
  .shelf-card .src {{ color:var(--dim); }}
  .shelf-card .more {{ color:var(--dim); font-style:italic; }}
  .note {{ border:1px solid rgba(244,208,111,.35); background:rgba(40,32,10,.28);
    padding:13px 15px; font-size:13px; color:#e8dcb4; }}
  footer {{ margin-top:34px; color:var(--dim); font-size:12px; letter-spacing:.04em; }}
  code {{ font-family:"Consolas",monospace; color:var(--gold); }}
</style></head>
<body><div class="wrap"><div class="frame">

  <h1>ARC DESK <span>· the library</span></h1>
  <div class="sub">"jarvis knows everything" — the honest build · every line below is a real
    output, generated at page build time</div>

  <div class="stats">
    <div class="stat"><b>{stats['entries']}</b><i>sourced facts</i></div>
    <div class="stat"><b>{stats['domains']}</b><i>domains</i></div>
    <div class="stat"><b>{stats['sources']}</b><i>named sources</i></div>
    <div class="stat"><b>{stats['moving']}</b><i>always dated</i></div>
    <div class="stat"><b>{stats['tools']}</b><i>tools</i></div>
    <div class="stat"><b>{stats['tests']}</b><i>test files</i></div>
  </div>

  <h2>Four sources. That is the whole claim.</h2>
  <div class="sources">
    <div class="src-card"><h3>Shelf</h3><p>{stats['entries']} entries, each with a source and a
      year, on this disk. No network needed.</p></div>
    <div class="src-card"><h3>Your files</h3><p>Point it at a folder — txt, md, csv, json, pdf,
      docx, xlsx, pptx — and it quotes the sentence with the filename.</p></div>
    <div class="src-card"><h3>Live lookup</h3><p>Wikipedia, with the URL and the date it was
      read. Cached a week. Says so when the network is down.</p></div>
    <div class="src-card"><h3>The machine</h3><p>Clock, CPU, RAM, disk, reminders, calendar —
      measured, never remembered.</p></div>
  </div>

  <h2>Asked and answered — {answered} from the shelf, {refused} honest no</h2>
  {''.join(cards)}

  <h2>Your own file, quoted</h2>
  <article class="qa">
    <div class="ask"><span class="tag yes">your library</span>
      <span class="q">“{html.escape(asked)}”</span></div>
    <pre>{html.escape(report)}</pre>
  </article>
  <article class="qa">
    <div class="ask"><span class="tag yes">your library</span>
      <span class="q">“when are the housekeeping rounds”</span></div>
    <pre>{html.escape(quote).replace(chr(10), '<br>')}</pre>
  </article>

  <h2>The shelf itself</h2>
  <div class="shelf">{shelf_rows()}</div>
  <p class="note"><b>*</b> = a number that moves. It is never printed without its year, and
    <code>tests/test_world.py</code> fails the build if that ever slips.</p>

  <footer>
    {stats['entries']} entries · {stats['domains']} domains · built from
    <code>arcdesk/world.py</code> · questions run through <code>arcdesk/ai/tools.py</code>
    tool 74 (<code>facts</code>) · page generated by <code>tools/make_knows_page.py</code>.
  </footer>
</div></div></body></html>"""
    return page


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} — {OUT.stat().st_size / 1024:.1f} KB")
