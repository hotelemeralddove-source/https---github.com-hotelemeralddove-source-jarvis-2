"""Eyes — read the screen, and click on what you read.

This is the piece that makes "click the blue button in Photoshop" possible without
any Photoshop-specific code: look at the pixels, find the words, click the words.
It works on every application, including games and remote desktops, because it
does not care what the app is.

Pipeline:

    screen_capture()  → PNG (Windows: .NET CopyFromScreen, Linux: scrot/import,
                            macOS: screencapture, fallback: Qt)
    ocr_words()       → [{text, x, y, w, h, conf}]  (Tesseract TSV, no Python dep)
    find_text()       → fuzzy-match the needle against those words, return a box
    click_at()        → move + click (PowerShell / xdotool / cliclick)

Honest limits, stated up front:

  * OCR reads **rendered text**. An icon-only button has no text; for those, use
    coordinates or a template image.
  * Pixels are physical; the mouse takes logical coordinates. `device_scale()`
    exists so a 150 %-scaled Windows laptop does not click 1.5× too far right.
  * Tesseract must be installed (`winget install UB-Mannheim.TesseractOCR` on
    Windows, `apt install tesseract-ocr` on Linux). Without it every function here
    says so instead of returning nonsense.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

from . import quiet
import sys
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

SHOT_DIR = Path(os.environ.get("ARCDESK_USER_HOME") or Path.home()) / "Pictures" / "ArcShots"


# ----------------------------------------------------------------- capture
def screen_capture(path: str = "") -> tuple[str, int, int]:
    """Grab the whole screen. Returns (path, width, height) or ("", 0, 0)."""
    target = Path(path) if path else SHOT_DIR / f"shot_{int(time.time() * 1000)}.png"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return "", 0, 0

    if IS_WIN:
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
            "$g=[System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($b.Left,$b.Top,0,0,$bmp.Size);"
            f"$bmp.Save('{str(target).replace(chr(92), '/')}',"
            "[System.Drawing.Imaging.ImageFormat]::Png);"
            "$g.Dispose();$bmp.Dispose()")
        _ps(ps, timeout=15)
    elif IS_MAC:
        _run(["screencapture", "-x", str(target)], timeout=15)
    else:
        tool = shutil.which("gnome-screenshot") or shutil.which("scrot") or shutil.which("import")
        if tool:
            _run([tool, str(target)], timeout=15)

    if not target.exists() or target.stat().st_size < 100:
        # last resort: Qt, which works on any platform with a display
        try:
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen is None:
                return "", 0, 0
            pix = screen.grabWindow(0)
            pix.save(str(target), "PNG")
        except Exception:
            return "", 0, 0
    if not target.exists():
        return "", 0, 0
    w, h = image_size(target)
    return str(target), w, h


def image_size(path: str | Path) -> tuple[int, int]:
    try:
        from PySide6.QtGui import QImage
        img = QImage(str(path))
        if not img.isNull():
            return img.width(), img.height()
    except Exception:
        pass
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return 0, 0


def device_scale() -> float:
    """Physical pixels per logical pixel — 1.5 on a 150 % Windows laptop."""
    try:
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            ratio = float(screen.devicePixelRatio() or 1.0)
            if IS_WIN and screen.logicalDotsPerInch() > 0:
                # Qt reports the DPI scaling; geometry is already in logical units
                dpi = screen.logicalDotsPerInch() / 96.0
                return max(ratio, dpi) if dpi > 0 else ratio
            return ratio
    except Exception:
        pass
    return 1.0


# ----------------------------------------------------------------- OCR
def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def _inverted_copy(path: str) -> str:
    """Tesseract expects dark text on light. Half of every real UI is the opposite."""
    try:
        from PIL import Image, ImageOps
    except Exception:
        return ""
    try:
        out = str(Path(path).with_name(Path(path).stem + "_inv.png"))
        with Image.open(path) as im:
            ImageOps.invert(im.convert("RGB")).save(out)
        return out
    except Exception:
        return ""


def _dedupe(primary: list[dict], extra: list[dict]) -> list[dict]:
    """Merge two OCR passes, dropping boxes that describe the same words twice."""
    def same(a: dict, b: dict) -> bool:
        ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
        bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]
        overlap = max(0, min(ax2, bx2) - max(a["x"], b["x"])) * \
                  max(0, min(ay2, by2) - max(a["y"], b["y"]))
        area = max(1, min(a["w"] * a["h"], b["w"] * b["h"]))
        return overlap / area > 0.5
    merged = list(primary)
    for word in extra:
        if not any(same(word, kept) for kept in merged):
            merged.append(word)
    return merged


def ocr_words(path: str, lang: str = "", invert: bool = True) -> list[dict]:
    """Word boxes from an image. Empty list (with a printed reason) when it cannot."""
    words = _ocr_pass(path, lang)
    if invert:
        inverted = _inverted_copy(path)
        if inverted:
            try:
                words = _dedupe(words, _ocr_pass(inverted, lang))
            finally:
                try:
                    Path(inverted).unlink()
                except Exception:
                    pass
    return words


def _ocr_pass(path: str, lang: str = "", psm: str = "6") -> list[dict]:
    if not ocr_available():
        return []
    exe = shutil.which("tesseract")
    cmd = [exe, str(path), "stdout", "--psm", psm, "tsv"]
    if lang:
        cmd = [exe, str(path), "stdout", "-l", lang, "--psm", psm, "tsv"]
    try:
        out = quiet.run(cmd, capture_output=True, text=True, timeout=45,
                             errors="replace")
    except Exception:
        return []
    words: list[dict] = []
    for line in (out.stdout or "").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) < 12:
            continue
        text = cols[11].strip()
        if not text:
            continue
        try:
            conf = float(cols[10])
        except ValueError:
            conf = 0.0
        if conf < 30:
            continue
        try:
            words.append({"text": text, "x": int(cols[6]), "y": int(cols[7]),
                          "w": int(cols[8]), "h": int(cols[9]), "conf": conf})
        except ValueError:
            continue
    return words


def screen_text(path: str = "", limit: int = 2000, lang: str = "") -> str:
    shot, w, h = screen_capture(path)
    if not shot:
        return "ERROR: could not capture the screen (no display, or no screenshot tool)"
    if not ocr_available():
        return ("ERROR: OCR needs Tesseract. Windows: winget install UB-Mannheim.TesseractOCR; "
                "Linux: sudo apt install tesseract-ocr. The screenshot is at " + shot)
    words = ocr_words(shot, lang)
    if not words:
        return f"no readable text on screen (captured {shot})"
    text = " ".join(w0["text"] for w0 in words)
    return text[:limit]


def ui_regions(path: str, limit: int = 24) -> list[tuple[int, int, int, int]]:
    """Find button-like rectangles: flat-coloured blocks that stand out from the page.

    This is the fix for the case that made the tiled pass useless — a white label on
    a saturated button is dropped by a page-wide layout analysis, and any tile grid
    that happens to cut the button in half cannot read it either. Detecting the
    *element* first and OCR-ing that exact rectangle (with a margin) reads it fine.
    """
    try:
        import numpy as np
        from PIL import Image
    except Exception:
        return []
    try:
        with Image.open(path) as im:
            small = im.convert("RGB")
            W, H = small.size
            arr = np.asarray(small, dtype=np.int16)
    except Exception:
        return []

    # background = the most common colour along the border
    border = np.concatenate([arr[0, :, :], arr[-1, :, :], arr[:, 0, :], arr[:, -1, :]])
    bg = np.median(border, axis=0)
    diff = np.abs(arr - bg).sum(axis=2)
    mask = diff > 90

    # cheap connected components: label with a numpy flood by rows/cols merging
    try:
        from scipy import ndimage            # fast path if scipy is around
        labels, n = ndimage.label(mask)
        slices = ndimage.find_objects(labels)
        boxes = []
        for sl in slices[:300]:
            if sl is None:
                continue
            y0, y1 = sl[0].start, sl[0].stop
            x0, x1 = sl[1].start, sl[1].stop
            boxes.append((x0, y0, x1 - x0, y1 - y0))
    except Exception:
        # numpy-only fallback: coarse block scan
        boxes = []
        step = 8
        for y in range(0, H, step):
            for x in range(0, W, step):
                block = mask[y:y + step, x:x + step]
                if block.mean() > 0.6:
                    boxes.append((x, y, step, step))

    picked: list[tuple[int, int, int, int]] = []
    for (x, y, w, h) in boxes:
        if w < 24 or h < 12:
            continue
        if w * h < 500:
            continue
        if w > W * 0.9 and h > H * 0.9:
            continue
        if max(w, h) / max(1, min(w, h)) > 14:
            continue
        picked.append((int(x), int(y), int(w), int(h)))
    picked.sort(key=lambda b: -(b[2] * b[3]))
    return picked[:limit]


def ocr_regions(path: str, scale: int = 2) -> list[dict]:
    """OCR each detected UI rectangle on its own, with a margin."""
    try:
        from PIL import Image
    except Exception:
        return []
    if not ocr_available():
        return []
    words: list[dict] = []
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            W, H = im.size
            for (x, y, w, h) in ui_regions(path):
                # exact box + psm 7 first: a margin of white around a coloured button
                # makes Tesseract return nothing at all (measured, not guessed)
                for (bx0, by0, bx1, by1, psm) in (
                        (x, y, x + w, y + h, "7"),
                        (x - 2, y - 2, x + w + 2, y + h + 2, "11")):
                    bx0, by0 = max(0, bx0), max(0, by0)
                    bx1, by1 = min(W, bx1), min(H, by1)
                    if bx1 - bx0 < 8 or by1 - by0 < 8:
                        continue
                    crop = im.crop((bx0, by0, bx1, by1))
                    big = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
                    tmp = str(Path(path).with_name(f"{Path(path).stem}_r{x}_{y}_{psm}.png"))
                    big.save(tmp)
                    found: list[dict] = []
                    try:
                        found = _ocr_pass(tmp, psm=psm)
                    finally:
                        try:
                            Path(tmp).unlink()
                        except Exception:
                            pass
                    for w0 in found:
                        w0 = dict(w0)
                        w0["x"] = w0["x"] // scale + bx0
                        w0["y"] = w0["y"] // scale + by0
                        w0["w"] = w0["w"] // scale
                        w0["h"] = w0["h"] // scale
                        words.append(w0)
                    if found:
                        break
    except Exception:
        return words
    return words


def ocr_tiles(path: str, cols: int = 3, rows: int = 2, scale: int = 2) -> list[dict]:
    """Second chance for text the full-screen pass missed.

    Tesseract segments by contrast across the whole page, so a white label on a
    saturated button can be dropped entirely. Cropping that region and doubling it
    recovers it (verified: "Save file" on a blue button goes from invisible to
    readable). Blank tiles are skipped, so the cost is usually 4-6 short passes.
    """
    try:
        from PIL import Image, ImageStat
    except Exception:
        return []
    if not ocr_available():
        return []
    words: list[dict] = []
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            W, H = im.size
            tile_w, tile_h = max(1, W // cols), max(1, H // rows)
            pad = int(tile_w * 0.10)
            for r in range(rows):
                for c in range(cols):
                    box = (max(0, c * tile_w - pad), max(0, r * tile_h - pad),
                           min(W, (c + 1) * tile_w + pad), min(H, (r + 1) * tile_h + pad))
                    crop = im.crop(box)
                    if max(ImageStat.Stat(crop.convert("L")).stddev) < 3.0:
                        continue                      # flat tile, nothing to read
                    big = crop.resize(((box[2] - box[0]) * scale,
                                       (box[3] - box[1]) * scale), Image.LANCZOS)
                    tmp = str(Path(path).with_name(f"{Path(path).stem}_t{r}{c}.png"))
                    big.save(tmp)
                    try:
                        for w0 in _ocr_pass(tmp):
                            w0 = dict(w0)
                            w0["x"] = w0["x"] // scale + box[0]
                            w0["y"] = w0["y"] // scale + box[1]
                            w0["w"] = w0["w"] // scale
                            w0["h"] = w0["h"] // scale
                            words.append(w0)
                    finally:
                        try:
                            Path(tmp).unlink()
                        except Exception:
                            pass
    except Exception:
        return words
    return words


_NORM = re.compile(r"[^a-z0-9 ]+")


def _norm(s: str) -> str:
    return " ".join(_NORM.sub(" ", (s or "").lower()).split())


def find_text(needle: str, words: list[dict]) -> dict | None:
    """Find the needle in OCR output. Exact substring first, then word overlap."""
    want = _norm(needle)
    if not want or not words:
        return None

    # 1. contiguous run of words that spells the needle
    joined = " ".join(_norm(w0["text"]) for w0 in words)
    idx = joined.find(want)
    if idx >= 0:
        start = len(joined[:idx].split())
        span = len(want.split())
        box = words[start:start + span]
        if box:
            return _merge(box)

    # 2. OCR often joins words ("accessisdenied") — match with spaces removed
    parts = [_norm(w0["text"]) for w0 in words]
    concat = ""
    starts: list[int] = []
    for part in parts:
        starts.append(len(concat))
        concat += part
    target = want.replace(" ", "")
    idx = concat.find(target) if target else -1
    if idx >= 0:
        end = idx + len(target)
        picked = [words[i] for i, start in enumerate(starts)
                  if start < end and start + len(parts[i]) > idx]
        if picked:
            return _merge(picked)

    # 3. single word, best fuzzy match
    if len(want.split()) == 1:
        best, score = None, 0.0
        import difflib
        for w0 in words:
            r = difflib.SequenceMatcher(None, want, _norm(w0["text"])).ratio()
            if r > score:
                best, score = w0, r
        if best and score >= 0.7:
            return dict(best)

    # 4. every needle word appears somewhere on screen (order-free)
    if all(any(p in part or part in p for part in parts) for p in want.split()):
        boxes = [w0 for w0 in words if _norm(w0["text"]) in want.split()]
        if boxes:
            return _merge(boxes)
    return None


def _merge(boxes: list[dict]) -> dict:
    x = min(b["x"] for b in boxes)
    y = min(b["y"] for b in boxes)
    x2 = max(b["x"] + b["w"] for b in boxes)
    y2 = max(b["y"] + b["h"] for b in boxes)
    return {"text": " ".join(b["text"] for b in boxes), "x": x, "y": y,
            "w": x2 - x, "h": y2 - y,
            "conf": max(b.get("conf", 0) for b in boxes)}


# ----------------------------------------------------------------- mouse
def click_at(x: int, y: int, button: str = "left", double: bool = False) -> str:
    x, y = int(x), int(y)
    if IS_WIN:
        flags = {"left": "0x2,0x4", "right": "0x8,0x10", "middle": "0x20,0x40"}.get(button, "0x2,0x4")
        times = 2 if double else 1
        ps = (
            "Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;"
            "public class M{[DllImport(\"user32.dll\")]public static extern bool SetCursorPos"
            "(int x,int y);[DllImport(\"user32.dll\")]public static extern void mouse_event"
            "(uint f,uint x,uint y,uint d,int e);}';"
            f"[M]::SetCursorPos({x},{y});"
            + "".join(f"[M]::mouse_event({flags.split(',')[0]},0,0,0,0);"
                      f"[M]::mouse_event({flags.split(',')[1]},0,0,0,0);" for _ in range(times)))
        out = _ps(ps)
    elif IS_MAC:
        exe = shutil.which("cliclick")
        if not exe:
            return "ERROR: clicking needs cliclick on macOS (brew install cliclick)"
        out = _run([exe, f"c:{x},{y}"]) if not double else _run([exe, "dc:" + f"{x},{y}"])
    else:
        exe = shutil.which("xdotool")
        if not exe:
            return "ERROR: clicking needs xdotool on Linux (sudo apt install xdotool)"
        out = _run([exe, "mousemove", str(x), str(y)])
        btn = {"left": "1", "middle": "2", "right": "3"}.get(button, "1")
        if double:
            out = _run([exe, "click", "--repeat", "2", "--delay", "80", btn])
        else:
            out += _run([exe, "click", btn])
    return out.strip() or f"clicked ({x}, {y})"


def click_text(needle: str, button: str = "left", double: bool = False,
               lang: str = "") -> str:
    """Look at the screen, find the words, click them."""
    shot, w, h = screen_capture()
    if not shot:
        return "ERROR: could not capture the screen"
    if not ocr_available():
        return ("ERROR: OCR needs Tesseract (winget install UB-Mannheim.TesseractOCR). "
                f"The screenshot is at {shot}")
    words = ocr_words(shot, lang)
    hit = find_text(needle, words)
    if not hit:
        # second pass: detect the UI rectangles and read each one on its own
        words = _dedupe(words, ocr_regions(shot))
        hit = find_text(needle, words)
    if not hit:
        # third pass: overlapping tiles, for text inside a large surface
        words = _dedupe(words, ocr_tiles(shot))
        hit = find_text(needle, words)
    if not hit:
        seen = " ".join(w0["text"] for w0 in words)[:180]
        return f"ERROR: could not find {needle!r} on screen. Visible text: {seen or '(none)'}"
    scale = device_scale()
    cx = int((hit["x"] + hit["w"] / 2) / scale)
    cy = int((hit["y"] + hit["h"] / 2) / scale)
    res = click_at(cx, cy, button=button, double=double)
    return (f"found {hit['text']!r} at ({cx}, {cy}) and clicked — {res}"
            if not res.lower().startswith("error") else res)


def _ps(script: str, timeout: float = 10.0) -> str:
    if not IS_WIN:
        return ""
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                 "-Command", script], timeout=timeout)


def _run(cmd, timeout: float = 10.0) -> str:
    try:
        out = quiet.run(cmd, capture_output=True, text=True, timeout=timeout,
                             errors="replace")
        return ((out.stdout or "").strip() or (out.stderr or "").strip())[:600]
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
