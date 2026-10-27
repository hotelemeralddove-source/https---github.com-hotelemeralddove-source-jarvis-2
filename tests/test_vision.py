"""Eyes — read the screen, find the words, aim at them.

Nothing here needs a display. A fake screenshot is drawn with known text at known
coordinates, which makes the assertions exact: the OCR either finds "Save file" on
the blue button or it does not, and the click target either lands inside the button
or it does not.

That button is the whole point of the file. White text on a saturated rectangle is
invisible to Tesseract's page segmentation — the first version of `find_text` missed
it completely. Region detection + OCR per rectangle is what fixed it, and this test
keeps it fixed.

Run:  python tests/test_vision.py
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("ARCDESK_USER_HOME", tempfile.mkdtemp(prefix="arcdesk-user-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path  # noqa: E402

from arcdesk import vision  # noqa: E402


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<50} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def check_true(label: str, got) -> bool:
    return check(label, bool(got), True)


def fake_screen() -> str:
    from PIL import Image, ImageDraw, ImageFont
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, 22) if Path(font_path).exists() else ImageFont.load_default()
    img = Image.new("RGB", (900, 320), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 260, 100], fill=(40, 90, 200))      # the blue button
    d.text((62, 58), "Save file", fill="white", font=font)
    d.text((40, 160), "Error 0x80070005: access is denied", fill="black", font=font)
    d.text((40, 230), "Photoshop   Settings   Export", fill=(30, 30, 30), font=font)
    out = Path(tempfile.mkdtemp(prefix="arcdesk-shot-")) / "screen.png"
    img.save(out)
    return str(out)


def main() -> int:
    ok = True
    shot = fake_screen()

    print("1) OCR reads ordinary text")
    words = vision.ocr_words(shot)
    ok &= check_true("words found", len(words) > 4)
    joined = " ".join(w["text"] for w in words).lower()
    ok &= check_true("reads the error line", "access" in joined and "denied" in joined)
    ok &= check_true("reads the menu words", "photoshop" in joined and "export" in joined)

    print("2) find_text matches, including words OCR glued together")
    for needle in ("Export", "Settings", "access is denied", "0x80070005"):
        hit = vision.find_text(needle, words)
        ok &= check_true(f"found {needle!r}", hit is not None)

    print("3) a coloured button is found by region detection, not by luck")
    regions = vision.ocr_regions(shot)
    merged = vision._dedupe(words, regions)
    hit = vision.find_text("Save file", merged)
    ok &= check_true("found 'Save file'", hit is not None)
    if hit:
        cx, cy = int(hit["x"] + hit["w"] / 2), int(hit["y"] + hit["h"] / 2)
        inside = 40 <= cx <= 260 and 40 <= cy <= 100
        ok &= check_true(f"click point ({cx},{cy}) is inside the button", inside)

    print("4) a word that is not there stays not found")
    ok &= check("miss reported honestly", vision.find_text("Cancel purchase", merged), None)
    ok &= check("empty needle", vision.find_text("", merged), None)

    print("5) rectangle detection finds the button and not the page")
    boxes = vision.ui_regions(shot)
    ok &= check_true("at least one region", len(boxes) >= 1)
    ok &= check_true("button box is in the list",
                     any(abs(x - 40) < 12 and abs(y - 40) < 12 for x, y, _w, _h in boxes))
    ok &= check_true("no box covers the whole screen",
                     all(not (w > 810 and h > 288) for _x, _y, w, h in boxes))

    print("6) scale and platform honesty")
    ok &= check_true("device scale is a positive number", vision.device_scale() > 0)
    if not vision.ocr_available():
        ok &= check("without Tesseract it says so",
                    vision.screen_text().lower().startswith("error"), True)
    else:
        print("   --   Tesseract present, engine check skipped")

    print("\n" + ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
