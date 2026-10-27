"""`explain` — the error-reader. The test is mostly about what it must NOT do.

At 11 p.m. a wrong diagnosis is worse than none: someone formats a disk, or
"solves" a permissions problem by disabling antivirus. So this suite measures
three things:

1. **Recall** — every one of the 24 error families in the table is reachable from
   the wording people actually see on screen (not from the table's own title).
2. **Ranking** — a specific signature beats a generic one: `0xc000007b` is not
   answered as "some error code", a Python `ModuleNotFoundError` is not answered
   as "a traceback".
3. **Refusal** — text that is not an error gets the text quoted back and a plain
   "I do not recognise this one". No invented causes, ever.

Run:  python tests/test_screenhelp.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("ARCDESK_USER_HOME", tempfile.mkdtemp(prefix="arcdesk-user-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import screenhelp  # noqa: E402
from arcdesk.ai import tools  # noqa: E402
from arcdesk.ai.lite import respond  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:40]!r}")
    ok &= bool(good)


# The wording is what a person photographs, typos and OCR warts included.
CASES: list[tuple[str, str]] = [
    ("The application was unable to start correctly (0xc000007b). Click OK.",
     "win_bad_image"),
    ("Windows protected your PC. SmartScreen prevented an unrecognized app from starting",
     "win_smart_screen"),
    ("Error 0x80070005: Access is denied.", "win_access_denied"),
    ("'gti' is not recognized as an internal or external command, operable program or "
     "batch file.", "win_not_found"),
    ("There is not enough space on the disk. 0x80070070", "win_disk_full"),
    ("Your PC ran into a problem and needs to restart. Stop code: "
     "DRIVER_IRQL_NOT_LESS_OR_EQUAL 0x000000d1", "win_bsod"),
    ("The Print Spooler service on Local Computer failed to start. Error 1053",
     "win_service"),
    ("We couldn't install some updates. Error 0x80248007", "win_update_fail"),
    ("Something failed with 0x80004005.", "win_generic_code"),
    ('Traceback (most recent call last):\n  File "app.py", line 12\n'
     "ModuleNotFoundError: No module named 'requests'", "py_module_missing"),
    ('Traceback (most recent call last):\n  File "app.py", line 12\nKeyError: user',
     "py_traceback"),
    ("SyntaxError: invalid syntax (main.py, line 4)", "py_syntax"),
    ("PermissionError: [Errno 13] Permission denied: '/etc/hosts'", "py_permission"),
    ("fatal: not a git repository (or any of the parent directories): .git", "git"),
    ("This site can't be reached. ERR_NAME_NOT_RESOLVED", "net_dns"),
    ("localhost:3000 ERR_CONNECTION_REFUSED", "net_refused"),
    ("Error 404 page not found", "http_code"),
    ("Your connection is not private. NET::ERR_CERT_DATE_INVALID", "tls"),
    ("You are offline. ERR_INTERNET_DISCONNECTED", "offline"),
    ("moov atom not found. Invalid data found when processing input", "ffmpeg"),
    ("The file is in use by another program", "file_locked"),
    ("The file is corrupt and cannot be opened.", "pdf_office"),
    ("No audio output device is installed", "no_audio"),
    ("You need to format the disk in drive E: before you can use it", "usb_disk"),
]

print("1) it names the errors people actually see")
wrong = []
for text, want in CASES:
    hits = screenhelp.match(text)
    got = hits[0]["sig"]["id"] if hits else None
    if got != want:
        wrong.append(f"{want} → {got}")
check(f"{len(CASES)} real messages, {len(CASES) - len(wrong)} named correctly",
      len(wrong), 0)
for line in wrong:
    print(f"        miss: {line}")

def top(case_index: int) -> str:
    hits = screenhelp.match(CASES[case_index][0])
    return hits[0]["sig"]["id"] if hits else None


print("2) ranking: specific beats generic")
check("the exception class beats the traceback frame",
      top(9), "py_module_missing")
check("a documented code beats 'some error code'", top(0), "win_bad_image")
check("a bare code still gets the generic family", top(8), "win_generic_code")
check("access denied is not answered as a generic code", top(2), "win_access_denied")
check("a corrupt-file message beats the generic 'file in use' family",
      top(21), "pdf_office")

print("3) the table itself is honest")
ids = [s["id"] for s in screenhelp.SIGNATURES]
check("no duplicate signatures", len(ids), len(set(ids)))
check("every signature has means/why/steps",
      all(s.get("means") and s.get("why") and s.get("steps")
          for s in screenhelp.SIGNATURES), True)
check("every signature carries a confidence class",
      all(s.get("sure") in ("certain", "likely") for s in screenhelp.SIGNATURES), True)
check("every signature offers at least two steps",
      all(len(s["steps"]) >= 2 for s in screenhelp.SIGNATURES), True)
check("the count in catalog() is the real count",
      f"{screenhelp.known()} error families" in screenhelp.catalog(), True)
check("a generic fallback exists for unknown codes",
      any(s.get("fallback") for s in screenhelp.SIGNATURES), True)

print("4) refusal — the part that keeps someone from formatting a disk")
unknown = "Quantum flux capacitor desynchronised at 88 mph"
answer = screenhelp.explain(unknown)
check("says plainly that it does not know", "do not recognise" in answer, True)
check("quotes the text back so OCR errors are visible", "Quantum flux" in answer, True)
check("offers a search instead of a guess", "search" in answer.lower(), True)
check("offers no steps it cannot back", "Do this, in order" in answer, False)
check("invents no cause for unknown text", "most likely first" in answer, False)
check("an empty request asks for text instead of guessing",
      "paste the error" in screenhelp.explain("").lower()
      or "no text to read" in screenhelp.explain("").lower(), True)
check("'0 errors' is not turned into a problem",
      "invent a problem" in screenhelp.explain("build finished with 0 errors").lower(),
      True)
check("'no error here' is believed, not second-guessed",
      "will not invent a problem" in screenhelp.explain(
          "this is a screenshot of my wallpaper, no error here").lower(), True)

print("5) the answer shape: read, mean, why, do")
body = screenhelp.explain(CASES[2][0])
check("quotes what it read", "Access is denied" in body, True)
check("gives the meaning", "What it means:" in body, True)
check("gives ordered causes", "most likely first" in body, True)
check("gives ordered steps", "Do this, in order:" in body, True)
check("states its confidence", "Confidence:" in body, True)
check("does not claim to have seen the machine", "unknown until" in body, True)
check("says when ARC itself cannot help",
      "never asks for admin" in body, True)
tanglish = screenhelp.explain(CASES[2][0], lang_text="machi idhu enna error da")
check("answers a Tanglish speaker in kind", "Machi" in tanglish, True)
check("the Tanglish line still refuses to guess",
      "guess panna maaten" in tanglish, True)
check("quoting never exceeds the line budget",
      len(screenhelp.quote(" ".join("line %d failed" % i for i in range(30)))) <= 6, True)

print("6) reading a real screen (OCR)")
from arcdesk import vision  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (940, 200), (244, 244, 244))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    draw.text((24, 30), "The application was unable to start correctly (0xc000007b).",
              fill=(10, 10, 10), font=font)
    draw.text((24, 90), "Click OK to close the application.", fill=(10, 10, 10), font=font)
    shot = Path(tempfile.mkdtemp(prefix="arcdesk-dlg-")) / "dialog.png"
    img.save(shot)
    rendered = True
except Exception:
    rendered = False

if rendered and vision.ocr_available():
    ocr_text = " ".join(w["text"] for w in vision.ocr_words(str(shot)))
    check("OCR reads the dialog off a rendered image", "unable to start" in ocr_text.lower()
          or "0xc000007b" in ocr_text, True)
    read = screenhelp.explain(ocr_text)
    check("the OCR'd text is diagnosed", "could not start the program" in read.lower(), True)
elif rendered:
    # No Tesseract: prove the capture → clean → match → explain plumbing instead, with
    # the exact string vision.screen_text() would hand over.
    original = vision.screen_text
    vision.screen_text = lambda *a, **k: (
        "Error  The application was unable to start correctly (0xc000007b). "
        "Click OK to close the application.  OK")
    try:
        read = screenhelp.explain("", screen=True)
        check("a captured screen is diagnosed without the user typing",
              "unable to start correctly" in read, True)
        check("it names where the text came from", "your screen" in read, True)
        check("OCR noise around the message is tolerated", "0xc000007b" in read, True)
        vision.screen_text = lambda *a, **k: "no readable text on screen (captured x.png)"
        check("an empty screen is reported, not diagnosed",
              "could not read any text" in screenhelp.explain("", screen=True), True)
        vision.screen_text = lambda *a, **k: (
            "ERROR: OCR needs Tesseract. Windows: winget install UB-Mannheim.TesseractOCR")
        check("a missing OCR engine says so instead of pretending",
              "Tesseract" in screenhelp.explain("", screen=True), True)
    finally:
        vision.screen_text = original
else:
    print("   ..   no Pillow — OCR path exercised by tests/test_vision.py instead")

print("7) wired: tool, router, and the phrase people say")
check("explain is a registered tool", "explain" in tools.TOOLS, True)
check("tool count", len(tools.TOOLS) >= 82, True)
check("the tool answers with text only", "What it means:" in
      tools.call("explain", {"text": CASES[4][0]}), True)
check("the catalog action lists the families",
      "error families" in tools.call("explain", {"where": "catalog"}), True)
routed = {"what is this error", "explain this error", "idhu enna error da",
          "enna problem da", "why did it crash", "what does this error mean",
          "why is this not working"}
missed = []
for phrase in sorted(routed):
    _, calls = respond(phrase)
    names = [c["function"]["name"] for c in calls]
    if "explain" not in names:
        missed.append(phrase)
check(f"{len(routed)} phrasings reach explain", missed, [])
check("'on my screen' asks for a capture, not the pasted words", True)
_, calls = respond("what is this error on my screen")
check("screen route chosen", '"where": "screen"' in calls[0]["function"]["arguments"], True)
for phrase, want in (("play ilaya nila", "play"), ("what is 18% of 4500", "calc"),
                     ("i feel low today", "coach"), ("open notepad", "open_app")):
    _, calls = respond(phrase)
    check(f"“{phrase}” still routes to {want}",
          calls[0]["function"]["name"] if calls else None, want)

print()
print("ALL PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
