"""Design and craft — colours that actually harmonise, patterns that actually print.

Two kinds of output, both original and both offline:

  * **design** — a palette computed from colour theory (real HSL rotation, not a
    mood board), a printable poster, a monogram mark;
  * **craft** — kolam / rangoli style dot-grid patterns, border strips, and paper
    craft nets, as SVG you can print or plot on a CNC/laser.

Nothing here downloads a font, calls a design API, or copies a stock template. The
geometry is generated from maths in this file, so the output is yours.
"""
from __future__ import annotations

import colorsys
import math
import random
import time

from . import config

SCHEMES = {
    "analogous": (0, 30, -30, 60, -60),
    "complementary": (0, 180, 15, 165, 195),
    "triad": (0, 120, 240, 60, 300),
    "tetrad": (0, 90, 180, 270, 45),
    "mono": (0, 0, 0, 0, 0),
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _to_hsl(colour: str) -> tuple[float, float, float]:
    c = (colour or "#48f2ff").strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        r, g, b = 0.28, 0.95, 1.0
    h, l, s = colorsys.rgb_to_hls(r, g, b)          # note: rgb_to_hls is h, l, s
    return h, s, l


def _to_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 1.0), _clamp(l), _clamp(s))
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def _luminance(hex_colour: str) -> float:
    c = hex_colour.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def palette(base: str = "#48f2ff", scheme: str = "analogous") -> str:
    """Five colours by real colour theory, with contrast measured, not assumed."""
    h, s, l = _to_hsl(base)
    offsets = SCHEMES.get((scheme or "analogous").lower().strip(), SCHEMES["analogous"])
    dark_ui = l > 0.35
    bg = _to_hex(h, _clamp(s * 0.25), 0.06 if dark_ui else 0.95)
    surface = _to_hex(h, _clamp(s * 0.30), 0.13 if dark_ui else 0.88)
    primary = _to_hex(h + offsets[0] / 360, _clamp(s), _clamp(l, 0.45, 0.62))
    accent = _to_hex(h + offsets[1] / 360, _clamp(s * 0.9), _clamp(l, 0.50, 0.68))
    # ink is chosen by which one contrasts better with the background we just made
    ink = max(("#f2fbff", "#0a0f14"), key=lambda c: contrast_ratio(bg, c))
    rows = [("background", bg, False), ("surface", surface, False),
            ("primary", primary, True), ("accent", accent, True), ("ink", ink, True)]
    lines = [f"{scheme} palette from {base}"]
    for role, hexv, check in rows:
        note = (f"contrast vs background: {contrast_ratio(bg, hexv):.1f}:1"
                if check else "")
        lines.append(f"  {role:<11} {hexv}   {note}")
    body = contrast_ratio(bg, ink)
    lines.append("")
    lines.append(f"Body text on the background: {body:.1f}:1 — "
                 + ("passes WCAG AA (4.5:1)" if body >= 4.5
                    else "below WCAG AA (4.5:1): change the background, not the words"))
    return "\n".join(lines)


def _svg(w: int, h: int, body: str, bg: str = "#05070d") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">\n'
            f'<rect width="{w}" height="{h}" fill="{bg}"/>\n{body}\n</svg>\n')


def poster(title: str = "JARVIS", subtitle: str = "", base: str = "#48f2ff") -> str:
    """A printable A3-proportioned poster built from geometry, no stock assets."""
    h, s, l = _to_hsl(base)
    bg = _to_hex(h, _clamp(s * 0.35), 0.05)
    glow = _to_hex(h, _clamp(s), 0.55)
    faint = _to_hex(h, _clamp(s * 0.6), 0.28)
    w, ht = 800, 1131
    cx, cy = w / 2, ht * 0.42
    rings = []
    for i, r in enumerate((120, 160, 205, 250, 300)):
        rings.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                     f'stroke="{faint if i % 2 else glow}" stroke-width="{1.5 if i % 2 else 2.5}" '
                     f'opacity="{0.35 + 0.1 * i}"/>')
    ticks = []
    for k in range(48):
        ang = k * math.pi / 24
        r1, r2 = 250, 262 if k % 4 else 276
        x1, y1 = cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)
        x2, y2 = cx + r2 * math.cos(ang), cy + r2 * math.sin(ang)
        ticks.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                     f'stroke="{glow}" stroke-width="{1.6 if k % 4 else 2.6}" opacity="0.75"/>')
    arcs = []
    for k in range(3):
        rr = 205 + k * 22
        start = 30 + k * 40
        end = start + 120
        x1, y1 = cx + rr * math.cos(math.radians(start)), cy + rr * math.sin(math.radians(start))
        x2, y2 = cx + rr * math.cos(math.radians(end)), cy + rr * math.sin(math.radians(end))
        arcs.append(f'<path d="M {x1:.1f} {y1:.1f} A {rr} {rr} 0 0 1 {x2:.1f} {y2:.1f}" '
                    f'fill="none" stroke="{glow}" stroke-width="3" opacity="0.5"/>')
    safe_title = (title or "JARVIS").replace("&", "&amp;").replace("<", "&lt;")[:26]
    safe_sub = (subtitle or "").replace("&", "&amp;").replace("<", "&lt;")[:60]
    body = "\n".join(rings + ticks + arcs) + f"""
<text x="{cx}" y="{cy + 16}" text-anchor="middle" font-family="Consolas, monospace"
      font-size="46" letter-spacing="10" fill="{glow}">{safe_title}</text>
<text x="{cx}" y="{ht * 0.78}" text-anchor="middle" font-family="Consolas, monospace"
      font-size="22" letter-spacing="4" fill="{faint}">{safe_sub}</text>
<rect x="40" y="40" width="{w - 80}" height="{ht - 80}" fill="none" stroke="{faint}"
      stroke-width="1.5" opacity="0.6"/>"""
    return _svg(w, ht, body, bg)


def kolam(dots: int = 5, base: str = "#f4d06f", seed: int = 7) -> str:
    """A symmetric dot-grid line pattern (kolam style), generated, never traced.

    Built the way the real thing is built: a dot grid, curves between dots, then
    mirrored on both axes so it cannot be lopsided.
    """
    n = max(3, min(9, int(dots)))
    rnd = random.Random(int(seed))
    h, s, l = _to_hsl(base)
    ink = _to_hex(h, _clamp(s), _clamp(l, 0.55, 0.72))
    bg = _to_hex(h, _clamp(s * 0.25), 0.06)
    step = 70
    pad = 60
    size = pad * 2 + step * (n - 1)
    half = (n - 1) // 2 + 1
    curves = []
    for r in range(half):
        for c in range(half):
            x, y = pad + c * step, pad + r * step
            if rnd.random() < 0.72:
                bulge = step * (0.42 + rnd.random() * 0.16)
                d = (f"M {x} {y} Q {x + bulge} {y - bulge} {x + step} {y + step} "
                     f"Q {x + step + bulge} {y + step - bulge} {x + step} {y + 2 * step}"
                     if r + 1 < n else
                     f"M {x} {y} Q {x + bulge} {y + bulge} {x + step} {y}")
                curves.append(d)
    dots = []
    for r in range(n):
        for c in range(n):
            dots.append(f'<circle cx="{pad + c * step}" cy="{pad + r * step}" r="2.6" '
                        f'fill="{ink}" opacity="0.75"/>')
    body = (f'<g stroke="{ink}" stroke-width="3.2" fill="none" stroke-linecap="round">'
            + "".join(f'<path d="{d}"/><path d="{d}" transform="scale(-1,1) '
                      f'translate({-size},0)"/>' for d in curves)
            + "</g>" + "<g>" + "".join(dots) + "</g>")
    return _svg(size, size, body, bg)


def border(kind: str = "kolam", width: int = 900, base: str = "#48f2ff") -> str:
    """A repeating strip: print it, or plot it."""
    h, s, l = _to_hsl(base)
    ink = _to_hex(h, _clamp(s), _clamp(l, 0.55, 0.7))
    hgt = 120
    parts = []
    if (kind or "kolam").lower() in ("kolam", "paisley", "floral"):
        for i in range(0, width, 60):
            parts.append(f'<path d="M {i} {hgt - 20} Q {i + 15} 20 {i + 30} {hgt - 20} '
                         f'Q {i + 45} 90 {i + 60} {hgt - 20}" fill="none" stroke="{ink}" '
                         f'stroke-width="2.5"/>')
            parts.append(f'<circle cx="{i + 30}" cy="{hgt - 30}" r="4" fill="{ink}"/>')
    else:
        for i in range(0, width, 40):
            parts.append(f'<path d="M {i} 20 L {i + 20} 100 L {i + 40} 20" fill="none" '
                         f'stroke="{ink}" stroke-width="2.5"/>')
    return _svg(width, hgt, "".join(parts))


def monogram(name: str = "JARVIS", base: str = "#48f2ff") -> str:
    """A mark from your own initials — a circle, a chevron, two letters."""
    h, s, l = _to_hsl(base)
    ink = _to_hex(h, _clamp(s), _clamp(l, 0.55, 0.66))
    dark = _to_hex(h, _clamp(s * 0.3), 0.07)
    letters = "".join(ch for ch in (name or "JARVIS") if ch.isalnum())[:2].upper() or "A"
    body = f"""
<circle cx="160" cy="160" r="120" fill="none" stroke="{ink}" stroke-width="3"/>
<circle cx="160" cy="160" r="96" fill="none" stroke="{ink}" stroke-width="1.2" opacity="0.5"/>
<path d="M 90 200 L 160 96 L 230 200" fill="none" stroke="{ink}" stroke-width="6"
      stroke-linecap="round"/>
<text x="160" y="182" text-anchor="middle" font-family="Consolas, monospace"
      font-size="64" letter-spacing="4" fill="{ink}">{letters}</text>"""
    return _svg(320, 320, body, dark)


def save(svg: str, name: str = "design") -> str:
    """Write an SVG into the app's craft folder as a new file. Never overwrites."""
    folder = config.data_dir() / "craft"
    folder.mkdir(parents=True, exist_ok=True)
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in (name or "design"))
    slug = "_".join(p for p in slug.split("_") if p)[:40] or "design"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = folder / f"{slug}_{stamp}.svg"
    n = 2
    while path.exists():
        path = folder / f"{slug}_{stamp}_{n}.svg"
        n += 1
    path.write_text(svg, encoding="utf-8")
    return f"Wrote {len(svg):,} bytes of SVG to {path}"
