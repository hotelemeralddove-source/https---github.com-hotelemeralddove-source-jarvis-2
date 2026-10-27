#!/usr/bin/env python3
"""Draw Arc Desk's icon — original artwork, generated, no third-party asset.

    python tools/make_icon.py

Writes `assets/arc_icon.png` (512) and `assets/arc_icon.ico` (multi-size, for
PyInstaller and Inno Setup). Pure Pillow; deterministic; cheap enough to run in CI.

Shape: concentric rings around a bright core — an arc-reactor *language* of light,
not a copy of any film prop. Cyan on near-black, matching the app's palette
(#48f2ff on #01050a) so the taskbar icon and the UI agree.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT_PNG = ROOT / "assets" / "arc_icon.png"
OUT_ICO = ROOT / "assets" / "arc_icon.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)

CYAN = (72, 242, 255)
CORE = (222, 253, 255)
DARK = (1, 5, 10)
RING = (18, 48, 61)


def draw_icon(size: int = 1024) -> Image.Image:
    ss = 4                                   # supersample, then shrink: clean edges
    n = size * ss
    img = Image.new("RGBA", (n, n), DARK + (255,))
    d = ImageDraw.Draw(img)

    c = n / 2
    # soft glow pool behind the reactor
    glow = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([c - n * 0.42, c - n * 0.42, c + n * 0.42, c + n * 0.42],
               fill=CYAN + (46,))
    glow = glow.filter(ImageFilter.GaussianBlur(n * 0.07))
    img.alpha_composite(glow)

    # outer housing: a dark disc so the icon reads on a light OR dark taskbar
    d.ellipse([c - n * 0.455, c - n * 0.455, c + n * 0.455, c + n * 0.455],
              fill=(3, 12, 18, 255), outline=RING + (255,), width=int(n * 0.012))

    # 10 coil segments around the ring, evenly spaced
    segments = 10
    for i in range(segments):
        a0 = (360 / segments) * i + 4
        a1 = a0 + (360 / segments) - 8
        box = [c - n * 0.365, c - n * 0.365, c + n * 0.365, c + n * 0.365]
        d.arc(box, a0, a1, fill=CYAN + (220,), width=int(n * 0.035))

    # inner triangle, faint — the "arc" of the name, drawn as a thin frame
    tri = [(c + n * 0.20 * math.cos(math.radians(-90 + 120 * k)),
            c + n * 0.20 * math.sin(math.radians(-90 + 120 * k))) for k in range(3)]
    d.polygon(tri, outline=CYAN + (110,), width=int(n * 0.014))

    # core
    for radius, alpha, colour in ((0.135, 70, CYAN), (0.100, 120, CYAN),
                                  (0.062, 210, CORE), (0.030, 255, (255, 255, 255))):
        r = n * radius
        d.ellipse([c - r, c - r, c + r, c + r], fill=colour + (alpha,))

    # a single specular streak, so the core looks lit and not flat
    sheen = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    sd.ellipse([c - n * 0.05, c - n * 0.085, c + n * 0.005, c - n * 0.025],
               fill=(255, 255, 255, 130))
    sheen = sheen.filter(ImageFilter.GaussianBlur(n * 0.012))
    img.alpha_composite(sheen)

    return img.resize((size, size), Image.LANCZOS)



def write_ico(frames: list, path) -> None:
    """Write a .ico that Windows Explorer actually draws.

    Pillow (12.x) writes EVERY frame as a PNG-compressed blob. That is legal, and Windows
    renders it at 256x256 — but the small frames it uses for a desktop shortcut (16, 32,
    48) are exactly where Explorer gives up and falls back to the *file type's* icon.
    The result is an exe that carries our icon and still shows PyInstaller's python.

    So: BMP/DIB frames (32-bit BGRA plus the 1-bit AND mask) for every size below 256,
    and PNG only for 256, which is the layout every icon tool on Windows produces.
    """
    import struct

    entries, blobs = [], []
    payload = b""
    offset = 6 + 16 * len(frames)
    for image in frames:
        size = image.size[0]
        rgba = image.convert("RGBA")
        if size >= 256:
            import io

            buf = io.BytesIO()
            rgba.save(buf, format="PNG")
            blob = buf.getvalue()
            bpp = 32
        else:
            w, h = rgba.size
            pixels = rgba.load()
            rows = []
            for y in range(h - 1, -1, -1):                 # DIB rows run bottom-up
                row = bytearray()
                for x in range(w):
                    r, g, b, a = pixels[x, y]
                    row += bytes((b, g, r, a))
                rows.append(bytes(row))
            xor = b"".join(rows)
            mask_row = ((w + 31) // 32) * 4                # 1bpp, padded to 4 bytes
            and_mask = b"".join(b"\x00" * mask_row for _ in range(h))
            header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0,
                                 len(xor) + len(and_mask), 0, 0, 0, 0)
            blob = header + xor + and_mask
            bpp = 32
        entries.append((size, bpp, len(blob), offset + len(payload)))
        payload += blob

    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    for size, bpp, length, where in entries:
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, bpp, length, where)
    out += payload
    path.write_bytes(bytes(out))


def main() -> int:
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    big = draw_icon(512)
    big.save(OUT_PNG)
    frames = [draw_icon(s) for s in SIZES]
    # NOT Pillow's save(): it writes every frame as PNG, and Explorer then refuses the
    # small sizes and shows the python instead. See write_ico's docstring.
    write_ico(frames, OUT_ICO)
    print(f"wrote {OUT_PNG.relative_to(ROOT)} ({OUT_PNG.stat().st_size // 1024} KB)")
    print(f"wrote {OUT_ICO.relative_to(ROOT)} ({OUT_ICO.stat().st_size // 1024} KB, "
          f"{len(SIZES)} sizes: {', '.join(str(s) for s in SIZES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
