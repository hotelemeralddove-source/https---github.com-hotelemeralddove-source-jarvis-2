#!/usr/bin/env python3
"""Generate the tools reference from the registry — never from memory.

    python tools/gen_tools_doc.py            # write TOOLS.md + arcdesk/TOOLS_PAGE.html
    python tools/gen_tools_doc.py --check    # exit 1 if either file is out of date

Why a generator: this project has already shipped three wrong counts in prose
("79 tools", "82 tools", "84 tools") because the number was typed by hand while the
registry grew. Anything a reader will quote has to be counted at build time.

The category table below is the only hand-written thing here, and it is *required* to
be exhaustive: a new tool that is not categorised makes this script fail loudly instead
of quietly landing in a "misc" bucket.
"""
from __future__ import annotations

import html
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-tools-"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk.ai import tools  # noqa: E402

MD_OUT = ROOT / "TOOLS.md"
HTML_OUT = ROOT / "arcdesk" / "TOOLS_PAGE.html"

# order matters: first section the reader meets should be the one they reach for first
CATEGORIES: list[tuple[str, str, tuple[str, ...]]] = [
    ("Talk to it", "The everyday things you type or say.", (
        "open_app", "open_url", "web_search", "time", "weather", "note", "read_notes",
        "clipboard", "profile", "calc", "convert", "list_tools",
    )),
    ("Machine control", "Volume, screen, power, windows and the keyboard.", (
        "system_report", "running_apps", "close_app", "set_volume", "mute", "media",
        "brightness", "screenshot", "lock_screen", "power", "timer", "windows",
        "type_text", "press", "action_log",
    )),
    ("The magical layer", "The bits that make it feel like a film.", (
        "magic", "charms", "arc_mode", "holo", "draw", "photo", "art_edit",
    )),
    ("Files, without risk", "Read-only by default; edits write a new file.", (
        "read_file", "edit_file", "find_file", "search_inside", "file_op",
        "file_delete", "run_command", "backup",
    )),
    ("Screen understanding", "OCR, controls and clicking — the machine-acting layer.", (
        "screen_text", "look", "click_text", "click_at", "ui_controls", "ui_act",
    )),
    ("Communication", "Mail, calendar, WhatsApp.", (
        "email_send", "email_draft", "calendar", "whatsapp_send",
    )),
    ("Media studio", "Local, free, ffmpeg-backed. No cloud, no account.", (
        "make_media", "video_studio", "audio_studio", "image_studio", "play", "library",
    )),
    ("Thinking tools", "Frameworks the model applies, with the arithmetic shown.", (
        "market", "stock", "project", "market_summary", "rates", "content", "marketing",
        "strategy", "hotel", "travel", "craft", "mine", "mentor", "foresight", "secure",
        "health", "coach", "explain", "teach_macro", "macros",
    )),
    ("Memory and day", "What it remembers, what it schedules.", (
        "remind", "focus", "briefing", "facts", "knows_placeholder", "vault",
    )),
    ("This machine, checked", "Measured, not guessed.", (
        "pc_health", "autostart", "mcp_servers", "packages", "plan",
    )),
]

# tools that belong to a section under a name that has since changed; kept honest
ALIASES = {"knows_placeholder": "facts"}


def section_of(name: str) -> str:
    for title, _line, members in CATEGORIES:
        if name in members:
            return title
    return ""


def catalogue() -> list[dict]:
    rows = []
    for name, tool in tools.TOOLS.items():
        params = []
        for arg, spec in (tool.params or {}).items():
            kind = spec.get("type", "string") if isinstance(spec, dict) else "string"
            enum = spec.get("enum") if isinstance(spec, dict) else None
            params.append({"name": arg, "type": kind, "enum": enum or [],
                           "required": arg in (tool.required or ())})
        rows.append({
            "name": name,
            "section": section_of(name),
            "description": (tool.description or "").strip(),
            "params": params,
            "confirm": bool(tool.confirm),
            "platforms": list(tool.platforms or ()),
        })
    return rows


def validate(rows: list[dict]) -> list[str]:
    problems = []
    known = {r["name"] for r in rows}
    for title, _line, members in CATEGORIES:
        for member in members:
            real = ALIASES.get(member, member)
            if real not in known:
                problems.append(f"category {title!r} lists a tool that does not exist: {member}")
    for row in rows:
        if not row["section"]:
            problems.append(f"tool {row['name']!r} is in no category — add it to CATEGORIES")
        if len(row["description"]) < 12:
            problems.append(f"tool {row['name']!r} has no usable description")
    return problems


# --------------------------------------------------------------- markdown
def build_md(rows: list[dict]) -> str:
    live = len(rows)
    confirmed = sum(1 for r in rows if r["confirm"])
    lines = [
        "# ARC DESK — every tool (generated)",
        "",
        f"**{live} tools.** Generated from `arcdesk/ai/tools.py` by",
        "`tools/gen_tools_doc.py` — do not edit this file, edit the registry and re-run.",
        "`check.bat` fails if this file is stale.",
        "",
        f"{confirmed} of them ask before acting (`confirm`). The other "
        f"{live - confirmed} only read.",
        "",
        "Call shape, everywhere:",
        "",
        "```",
        'tools.call("set_volume", {"level": 40})',
        "```",
        "",
        "`call()` never raises; it returns a sentence you can read out loud.",
        "",
    ]
    for title, blurb, _members in CATEGORIES:
        group = [r for r in rows if r["section"] == title]
        if not group:
            continue
        lines += [f"## {title} ({len(group)})", "", blurb, ""]
        for row in group:
            flag = " · **asks first**" if row["confirm"] else ""
            plat = f" · only {', '.join(row['platforms'])}" if row["platforms"] else ""
            lines.append(f"### `{row['name']}`{flag}{plat}")
            lines.append("")
            lines.append(row["description"])
            lines.append("")
            if row["params"]:
                lines.append("| argument | type | required | values |")
                lines.append("|---|---|---|---|")
                for p in row["params"]:
                    vals = ", ".join(f"`{v}`" for v in p["enum"]) if p["enum"] else "—"
                    lines.append(f"| `{p['name']}` | {p['type']} | "
                                 f"{'yes' if p['required'] else 'no'} | {vals} |")
                lines.append("")
    lines += ["---", "",
              "Counts here are computed at build time. If you want to know what is",
              "actually *working on this machine right now*, run "
              "`python tools/capability.py --all`.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------- html
CSS = """
:root{--bg:#01050a;--ink:#dff6ff;--dim:#6d8797;--arc:#48f2ff;--line:#12303d;
      --warn:#ffb03a;--card:#040d14}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 50% -20%,#062733 0%,var(--bg) 55%);
     color:var(--ink);font:15px/1.55 "Segoe UI",system-ui,sans-serif;padding:28px 22px 64px}
h1{font-size:26px;letter-spacing:.14em;text-transform:uppercase;margin:0 0 4px;
   font-weight:600}
h1 span{color:var(--arc)}
.sub{color:var(--dim);margin:0 0 18px;font-size:13px}
.bar{position:sticky;top:0;z-index:5;background:linear-gradient(#01050aee,#01050acc);
     backdrop-filter:blur(6px);padding:12px 0 14px;border-bottom:1px solid var(--line);
     display:flex;gap:10px;flex-wrap:wrap;align-items:center}
input,select{background:var(--card);border:1px solid var(--line);color:var(--ink);
     border-radius:8px;padding:9px 12px;font:inherit;outline:none}
input{flex:1 1 260px;min-width:180px}
input:focus,select:focus{border-color:var(--arc);box-shadow:0 0 0 3px #48f2ff22}
.count{color:var(--dim);font-size:13px;white-space:nowrap}
.chip{border:1px solid var(--line);border-radius:999px;padding:5px 12px;cursor:pointer;
     font-size:13px;color:var(--dim);background:transparent}
.chip[aria-pressed=true]{border-color:var(--arc);color:var(--bg);background:var(--arc);
     font-weight:600}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));
     margin-top:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 15px}
.card:hover{border-color:#1d5a6e}
.card h3{margin:0 0 6px;font:600 15px/1.3 "Cascadia Code",ui-monospace,monospace;
     color:var(--arc);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.tag{font:500 10px/1 "Segoe UI",sans-serif;letter-spacing:.1em;text-transform:uppercase;
     border:1px solid var(--warn);color:var(--warn);border-radius:999px;padding:4px 7px}
.tag.os{border-color:#5a7d8c;color:#8fb0be}
.desc{color:#b9d4e0;font-size:13.5px;margin:0 0 10px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
td{padding:3px 6px 3px 0;vertical-align:top;border-top:1px solid #0c2029}
td:first-child{font-family:"Cascadia Code",ui-monospace,monospace;color:#e9fbff;width:34%}
td.ty{color:var(--dim);width:20%}
td.rq{width:44px;color:var(--arc)}
.enum{color:#88a9b8}
h2{font-size:14px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);
   margin:34px 0 6px;font-weight:600}
.sec{color:var(--dim);font-size:13px;margin:0 0 4px}
.none{color:var(--dim);padding:26px 0}
footer{margin-top:44px;color:var(--dim);font-size:12.5px;border-top:1px solid var(--line);
   padding-top:14px}
code{font-family:"Cascadia Code",ui-monospace,monospace;color:var(--arc)}
"""

JS = """
const cards = [...document.querySelectorAll('.card')];
const q = document.getElementById('q');
const yes = document.getElementById('yes');
const cat = document.getElementById('cat');
const chips = [...document.querySelectorAll('.chip')];
const count = document.getElementById('count');
const none = document.getElementById('none');
let asksOnly = false, section = '';

function apply() {
  const term = q.value.trim().toLowerCase();
  let shown = 0;
  for (const c of cards) {
    const text = c.dataset.text;
    let ok = !term || text.includes(term);
    if (ok && asksOnly) ok = c.dataset.confirm === '1';
    if (ok && section && c.dataset.section !== section) ok = false;
    c.hidden = !ok;
    if (ok) shown++;
  }
  for (const sec of document.querySelectorAll('section[data-section]')) {
    const key = sec.dataset.section;
    sec.hidden = !cards.some(c => c.dataset.section === key && !c.hidden);
  }
  count.textContent = shown + ' of ' + cards.length + ' tools';
  none.hidden = shown !== 0;
}
q.addEventListener('input', apply);
yes.addEventListener('change', () => { asksOnly = yes.checked; apply(); });
cat.addEventListener('change', () => { section = cat.value; apply(); });
for (const chip of chips) {
  chip.addEventListener('click', () => {
    section = chip.dataset.section;
    cat.value = section;
    chips.forEach(c => c.setAttribute('aria-pressed', String(c.dataset.section === section)));
    apply();
    chip.blur();
  });
}
document.addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement !== q) { e.preventDefault(); q.focus(); }
  if (e.key === 'Escape') { q.value = ''; apply(); }
});
apply();
"""


def build_html(rows: list[dict]) -> str:
    sections = [(t, b) for t, b, _m in CATEGORIES if any(r["section"] == t for r in rows)]
    opts = "".join(f'<option value="{html.escape(t)}">{html.escape(t)}</option>'
                   for t, _b in sections)
    chips = ('<button class="chip" data-section="" aria-pressed="true">all</button>'
             + "".join(f'<button class="chip" data-section="{html.escape(t)}" '
                       f'aria-pressed="false">{html.escape(t)}</button>'
                       for t, _b in sections))
    out = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        "<title>Arc Desk — tools</title><style>", CSS, "</style></head><body>",
        '<h1>Arc Desk <span>·  every tool</span></h1>',
        f'<p class="sub">{len(rows)} tools, generated from the registry at build time. '
        f'Press <code>/</code> to search, <code>Esc</code> to clear.</p>',
        '<div class="bar">',
        '<input id="q" type="search" placeholder="search: backup, pdf, video, volume, ocr…" '
        'autocomplete="off" aria-label="search tools">',
        f'<select id="cat" aria-label="section"><option value="">every section</option>'
        f'{opts}</select>',
        '<label class="count"><input id="yes" type="checkbox" style="vertical-align:-1px"> '
        'asks first only</label>',
        '<span id="count" class="count"></span>',
        "</div><div class=\"bar\" style=\"position:static;border:0;padding-top:0\">",
        chips, "</div>",
    ]
    for title, blurb in sections:
        group = [r for r in rows if r["section"] == title]
        esc = html.escape(title)
        out.append(f'<section data-section="{esc}"><h2>{esc} ({len(group)})</h2>'
                   f'<p class="sec">{html.escape(blurb)}</p>')
        out.append('<div class="grid">')
        for row in group:
            text = " ".join([row["name"], row["description"],
                             " ".join(p["name"] for p in row["params"]),
                             " ".join(str(v) for p in row["params"] for v in p["enum"])]
                            ).lower()
            tags = ""
            if row["confirm"]:
                tags += '<span class="tag">asks first</span>'
            if row["platforms"]:
                tags += f'<span class="tag os">{html.escape(", ".join(row["platforms"]))}</span>'
            out.append(f'<div class="card" data-section="{esc}" data-confirm="'
                       f'{int(row["confirm"])}" data-text="{html.escape(text, quote=True)}">')
            out.append(f'<h3>{html.escape(row["name"])}{tags}</h3>')
            out.append(f'<p class="desc">{html.escape(row["description"])}</p>')
            if row["params"]:
                out.append("<table>")
                for p in row["params"]:
                    rq = "●" if p["required"] else ""
                    enum = ('<span class="enum">' + " · ".join(html.escape(str(v))
                            for v in p["enum"]) + "</span>") if p["enum"] else ""
                    out.append(f'<tr><td>{html.escape(p["name"])}</td>'
                               f'<td class="ty">{html.escape(p["type"])}</td>'
                               f'<td class="rq">{rq}</td><td>{enum}</td></tr>')
                out.append("</table>")
            out.append("</div>")
        out.append("</section>")
    out += [
        '<p id="none" class="none" hidden>Nothing matches that. Try a shorter word — '
        'or ask Arc Desk itself: "list tools".</p>',
        '<footer>Generated by <code>tools/gen_tools_doc.py</code> from '
        '<code>arcdesk/ai/tools.py</code>. Counts are counted, not typed. '
        'To see what is actually working on this machine, run '
        '<code>python tools/capability.py --all</code>. '
        '● = required argument. Works offline; no network, no fonts, no CDN.</footer>',
        "<script>", JS, "</script></body></html>",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    rows = catalogue()
    problems = validate(rows)
    if problems:
        print("ARC DESK · tools reference")
        for line in problems:
            print("  FAIL", line)
        print("Nothing was written. Fix the registry or the category table.")
        return 1
    md = build_md(rows)
    page = build_html(rows)
    if "--check" in args:
        stale = []
        for path, want in ((MD_OUT, md), (HTML_OUT, page)):
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have != want:
                stale.append(path.name)
        if stale:
            print("tools reference is STALE: " + ", ".join(stale))
            print("run: python tools/gen_tools_doc.py")
            return 1
        print(f"tools reference is current — {len(rows)} tools, "
              f"{len(CATEGORIES)} sections, 0 mismatch")
        return 0
    MD_OUT.write_text(md, encoding="utf-8")
    HTML_OUT.write_text(page, encoding="utf-8")
    confirmed = sum(1 for r in rows if r["confirm"])
    print(f"wrote {MD_OUT.relative_to(ROOT)} ({len(md) // 1024} KB, {len(rows)} tools)")
    print(f"wrote {HTML_OUT.relative_to(ROOT)} ({len(page) // 1024} KB)")
    print(f"{len(CATEGORIES)} sections · {confirmed} ask first · "
          f"{len(rows) - confirmed} read-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
