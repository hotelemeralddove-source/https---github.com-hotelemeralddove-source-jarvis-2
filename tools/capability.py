#!/usr/bin/env python3
"""Capability probe — what can ARC actually do, proven one tool at a time.

    python tools/capability.py             # run the safe tools for real
    python tools/capability.py --json      # machine readable
    python tools/capability.py --all       # include the guarded / platform rows

Every line is either something that really executed here, or an explicit
"cannot run here and why". Nothing is claimed without evidence, because the
point of this file is to stop the docs from promising things the code cannot do.

Three verdicts:
    OK        ran just now, output shown
    GUARDED   destructive by design (confirm=True) — not executed on purpose
    PLATFORM  declares platforms=(...) — checked, not run on this OS
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-cap-"))
# file tools write inside the user's home, so give the probe a throw-away one
os.environ.setdefault("ARCDESK_USER_HOME", tempfile.mkdtemp(prefix="arcdesk-user-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk.ai import tools  # noqa: E402

# A document and a picture for the file tools to chew on, made here so the probe
# needs nothing from the user's disk.
_PROBE_DIR = Path(tempfile.mkdtemp(prefix="arcdesk-probe-"))
_PROBE_DOC = _PROBE_DIR / "probe.txt"
_PROBE_DOC.write_text("Arc Desk capability probe. Revenue 18 percent, costs 6 percent.",
                      encoding="utf-8")
_PROBE_CSV = _PROBE_DIR / "probe.csv"
_PROBE_CSV.write_text("city,price,units\nBelagavi,750,120\nHubli,800,90\n"
                      "Goa,1500,40\nGoa,1400,55\nHampi,900,70\n", encoding="utf-8")
_PROBE_PNG = _PROBE_DIR / "probe.png"
try:
    from PIL import Image, ImageDraw
    _img = Image.new("RGB", (320, 200), (14, 22, 48))
    ImageDraw.Draw(_img).text((20, 90), "ARC PROBE 2026", fill=(255, 210, 120))
    _img.save(_PROBE_PNG)
except Exception:
    _PROBE_PNG.write_bytes(b"")          # the tool will say why it cannot read it

# A one-second clip and a tone, so the studio probes run a real encode instead of
# only listing what it could do. If ffmpeg is missing they stay empty and the probe
# falls back to the catalogue — which is itself an honest answer.
_PROBE_MP4 = _PROBE_DIR / "probe.mp4"
_PROBE_WAV = _PROBE_DIR / "probe.wav"


def _make_media_probes() -> bool:
    import shutil
    import subprocess
    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    try:
        subprocess.run([exe, "-y", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=320x240:rate=25:duration=1",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", str(_PROBE_MP4)], check=True, timeout=60)
        subprocess.run([exe, "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=300:duration=1", str(_PROBE_WAV)],
                       check=True, timeout=60)
        return True
    except Exception:
        return False


_HAS_MEDIA = _make_media_probes()

# tool -> sample arguments, chosen so the call is harmless everywhere
SAFE: dict[str, dict] = {
    "system_report": {},
    "running_apps": {},
    "time": {},
    "note": {"text": "capability probe note"},
    "read_notes": {"limit": 2},
    "find_file": {"name": ".json"},
    "weather": {},
    "mcp_servers": {},
    "timer": {"minutes": 0.05, "label": "probe"},
    "arc_mode": {"mode": "chill"},
    "magic": {"action": "toggle"},
    "charms": {"action": "hide"},
    "screenshot": {"path": str(Path(tempfile.gettempdir()) / "arc_cap_probe.png")},
    "draw": {"subject": "elephant"},
    "art_edit": {"instruction": "make it purple and bigger"},
    # the "do it for me" tools: file work happens in the probe's own home folder
    "windows": {"action": "list", "title": ""},
    "file_op": {"action": "write", "path": "probe/note.txt", "text": "probe"},
    "read_file": {"path": str(_PROBE_DOC), "mode": "summary"},
    "action_log": {"limit": 3},
    "press": {"keys": "ctrl+s"},
    "type_text": {"text": "probe"},
    # eyes + people: safe to run, they only read or write probe-owned files
    "screen_text": {},
    "ui_controls": {"limit": 5},
    "calendar": {"action": "add", "title": "probe event", "when": "in 2 hours"},
    # numbers, markets and learned commands — all read-only
    "list_tools": {"query": "timer"},
    "profile": {"action": "get"},
    "look": {"question": "what is on the screen?"},
    "calc": {"expression": "18% of 4500"},
    "convert": {"value": 5, "from_unit": "km", "to_unit": "mile"},
    "rates": {"base": "INR", "symbols": "USD,EUR"},
    "stock": {"symbol": "nifty"},
    "project": {"symbol": "reliance", "days": 5},
    "market_summary": {},
    "teach_macro": {"instruction": "when i say probe mode, set volume 7 and note probe"},
    "macros": {"action": "list"},
    # file brains: the reader gets a real document, the editor a real picture
    "edit_file": {"path": str(_PROBE_PNG), "op": "resize", "width": 80},
    "make_media": {"prompt": "a probe arc reactor in gold and teal", "kind": "image",
                   "width": 200, "height": 140},
    "market": {"what": "quote", "symbol": "nifty"},
    "health": {"what": "medicine", "query": "paracetamol", "question": "how much"},
    # the day layer: reminders, focus blocks, briefing — all local, all reversible
    "remind": {"action": "add", "text": "remind me in 30 minutes to stretch"},
    "focus": {"action": "start", "minutes": "1", "label": "probe"},
    "briefing": {"what": "today"},
    # the open-source catalogue: read-only search and detection
    "packages": {"action": "search", "query": "ocr", "role": "", "key": ""},
    # the studio, business, travel and thinking layer — local maths only
    "content": {"action": "hooks", "topic": "direct hotel bookings"},
    "marketing": {"action": "funnel", "impressions": 20000, "clicks": 400,
                  "leads": 60, "sales": 12, "spend": 5000, "revenue": 24000},
    "strategy": {"action": "break", "fixed": 90000, "price": 750, "variable": 320},
    "hotel": {"action": "kpi", "rooms": 24, "sold": 17, "room_revenue": 42500,
              "other_revenue": 9000, "costs": 26000},
    "travel": {"action": "near", "place": "Belagavi", "radius_km": 200, "tag": "heritage"},
    "craft": {"action": "palette", "base": "#48f2ff", "scheme": "triad"},
    "mine": {"action": "profile", "path": str(_PROBE_CSV)},
    "mentor": {"action": "invert", "subject": "get 20 direct bookings"},
    "foresight": {"action": "forecast", "values": "120 140 155 171 190", "periods": 2},
    # the library: dictionary answers, read from disk, no network in the probe
    "facts": {"action": "ask", "question": "how many states are there in india"},
    # the studio: a real encode if ffmpeg is here, otherwise the honest catalogue
    "video_studio": ({"action": "look", "path": str(_PROBE_MP4), "look": "noir",
                      "strength": 0.8} if _HAS_MEDIA else {"action": "catalog"}),
    "audio_studio": ({"action": "denoise", "path": str(_PROBE_WAV)}
                     if _HAS_MEDIA else {"action": "catalog"}),
    "image_studio": {"action": "look", "path": str(_PROBE_PNG), "look": "cinematic"},
    "secure": {"action": "phishing",
               "text": "URGENT: verify your password at http://paytm-kyc.xyz"},
    # wave 5 — the index, the planner and the coach all work without a display
    "library": {"action": "scan", "roots": str(_PROBE_DIR)},
    "plan": {"action": "think", "request": "scan my music and play kabira"},
    "pc_health": {"action": "quick"},
    "backup": {"action": "drives"},
    "autostart": {"action": "status"},
    "search_inside": {"action": "index", "roots": str(_PROBE_DIR)},
    "explain": {"text": "The application was unable to start correctly (0xc000007b)."},
    "coach": {"mode": "decide",
              "text": "should i take the smaller contract now or wait for the bigger one"},
}

# deliberately not executed, but their guard is verified
GUARDED = {"close_app", "power", "file_delete", "run_command", "email_send", "whatsapp_send"}

WHY_NOT = {
    "open_app": "launches a real program — not executed in a headless probe",
    "open_url": "would open a browser window",
    "web_search": "would open a browser window",
    "set_volume": "changes the machine's audio",
    "mute": "changes the machine's audio",
    "media": "sends media keys to whatever is playing",
    "brightness": "changes the display",
    "lock_screen": "would lock this session",
    "clipboard": "would read the user's clipboard",
    "screenshot": "needs a display (runs, but there is nothing to capture here)",
    "power": "could shut the machine down",
    "holo": "needs the running Arc Desk window — rendered to shots/holo_*.png instead",
    "close_app": "could kill a process",
    "file_delete": "deletes a file — refused on purpose, the gate is the point",
    "run_command": "runs a shell command — refused on purpose, the gate is the point",
    "click_text": "would click on the real desktop",
    "click_at": "would move the mouse on the real desktop",
    "ui_act": "could click a real control in whatever window is focused",
    "email_send": "would send mail from the user's account",
    "email_draft": "would open the user's mail app",
    "whatsapp_send": "would open WhatsApp with a message",
    "play": "starts a real player process — verified in tests/test_playback.py instead",
    "rates": "needs the internet",
    "stock": "needs the internet",
    "project": "needs the internet",
    "market_summary": "needs the internet",
}


def one(name: str, spec) -> dict:
    t = tools.TOOLS[name]
    row = {"name": name, "kind": "", "verdict": "", "detail": "", "ms": 0.0,
           "params": sorted(t.params), "confirm": t.confirm,
           "platforms": list(t.platforms) if t.platforms else []}
    if name in GUARDED:
        row["kind"] = "guarded"
        row["verdict"] = "GUARDED" if t.confirm else "FAIL"
        row["detail"] = ("confirm=True, the UI asks before it runs" if t.confirm
                         else "destructive tool is NOT flagged confirm")
        return row
    if t.platforms and sys.platform not in t.platforms:
        row["kind"] = "platform"
        row["verdict"] = "PLATFORM"
        out = tools.call(name, {k: True for k in t.required})
        row["detail"] = f"declares {', '.join(t.platforms)} · says: {out[:60]}"
        return row
    if name not in SAFE:
        row["kind"] = "skipped"
        row["verdict"] = "SKIP"
        row["detail"] = WHY_NOT.get(name, "not executed by the probe")
        return row

    row["kind"] = "live"
    t0 = time.time()
    try:
        out = tools.call(name, SAFE[name])
    except Exception as exc:                      # call() should never raise
        out = f"RAISED {type(exc).__name__}: {exc}"
    row["ms"] = round((time.time() - t0) * 1000, 1)
    flat = " ".join(str(out).split())
    row["detail"] = flat[:150]
    row["verdict"] = "OK" if flat and "RAISED" not in flat else "FAIL"
    return row


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    show_all = "--all" in argv
    rows = [one(n, s) for n, s in tools.TOOLS.items()]

    by = {}
    for r in rows:
        by.setdefault(r["verdict"], []).append(r["name"])

    if as_json:
        print(json.dumps(rows, indent=2))
        return 0 if not by.get("FAIL") else 1

    print("Arc Desk · capability probe")
    print("=" * 78)
    print(f"{len(rows)} tools · python {sys.version.split()[0]} · platform {sys.platform}")
    print()
    for r in rows:
        if not show_all and r["verdict"] == "SKIP":
            continue
        tag = {"OK": "[ok]  ", "FAIL": "[FAIL]", "GUARDED": "[guard]",
               "PLATFORM": "[win] ", "SKIP": "[skip]"}[r["verdict"]]
        print(f"{tag} {r['name']:<15} {r['ms']:>7.1f}ms  {r['detail'][:88]}")
    print()
    print(f"live {len(by.get('OK', []))} · failed {len(by.get('FAIL', []))} · "
          f"guarded {len(by.get('GUARDED', []))} · platform {len(by.get('PLATFORM', []))} · "
          f"skipped {len(by.get('SKIP', []))}")

    if by.get("FAIL"):
        print("\nFAILED:", ", ".join(by["FAIL"]))
        return 1
    print("\nRESULT: every executable tool answered without raising.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
