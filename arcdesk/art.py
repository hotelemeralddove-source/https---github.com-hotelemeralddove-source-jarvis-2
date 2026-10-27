"""JARVIS Sketch — drawing that actually draws, offline, in a few milliseconds.

Why not a diffusion model? Because 4 GB of VRAM is not a fair ask, and "JARVIS cannot
draw at all" is a worse answer than "JARVIS draws a clean vector sketch and lets you
edit it by talking". So this is a small, deterministic drawing language:

    a document  = { subject, accent, scale, offset, extras, rotation }
    a subject   = a list of primitives in 0..1 space (ellipse, poly, curve, ...)
    rendering   = QPainter on a QImage, any resolution, no assets, no network

That structure is what makes **editing** possible. A prompt like "make it purple
and bigger" mutates three numbers in the document and re-renders; it never needs
to regenerate pixels. Undo is a snapshot of a dict.

If a real image model is running locally (ComfyUI, Automatic1111, Fooocus), it is
detected and can be used instead — see `image_backends()`. Otherwise this is the
answer, and it works on any laptop from 2010 onwards.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

PALETTE = {
    "grey": "#9aa7b4", "gray": "#9aa7b4", "blue": "#4fa3e3", "cyan": "#38d6e8",
    "purple": "#a07cf0", "violet": "#a07cf0", "pink": "#f07cb0", "red": "#e85d5d",
    "orange": "#f09a4f", "amber": "#f0b429", "yellow": "#f5d76e", "gold": "#e8c26a",
    "green": "#5fd08a", "mint": "#7ce0b8", "teal": "#3fbfa8", "brown": "#a9744f",
    "white": "#f2f6fa", "cream": "#efe4cf", "black": "#20262e", "silver": "#c9d3dd",
}

SUBJECTS = {
    "elephant": ("elephant", "aane", "haathi", "yane", "elephants"),
    "cat": ("cat", "pilli", "bekku", "kitten", "cats"),
    "dog": ("dog", "naayi", "puppy", "dogs"),
    "house": ("house", "home", "mane", "cottage"),
    "tree": ("tree", "maram", "plant"),
    "flower": ("flower", "hoo", "rose", "sunflower"),
    "car": ("car", "gaadi", "vehicle"),
    "robot": ("robot", "android", "bot"),
    "fish": ("fish", "meenu", "machhli"),
    "sun": ("sun", "surya", "sunshine"),
}

ALIAS = {a: subj for subj, names in SUBJECTS.items() for a in names}


# --------------------------------------------------------------- primitives
def _ellipse(cx, cy, rx, ry, fill, line=None, lw=0.006):
    return ("ellipse", cx, cy, rx, ry, fill, line, lw)


def _rect(x, y, w, h, fill, line=None, lw=0.006, r=0.0):
    return ("rect", x, y, w, h, fill, line, lw, r)


def _poly(points, fill, line=None, lw=0.006):
    return ("poly", points, fill, line, lw)


def _curve(points, stroke, lw=0.014, fill=None):
    return ("curve", points, stroke, lw, fill)


def _circle(cx, cy, r, fill, line=None, lw=0.006):
    return _ellipse(cx, cy, r, r, fill, line, lw)


# ----------------------------------------------------------------- subjects
def _elephant(c: str, d: str) -> list:
    """Facing right: wide body, four legs, big ear, curled trunk, tusk, tail."""
    return [
        _ellipse(0.44, 0.75, 0.30, 0.035, "#00000033"),         # ground shadow
        _rect(0.24, 0.58, 0.105, 0.19, _shade(c, 0.90), d, r=0.03),   # far legs
        _rect(0.55, 0.58, 0.105, 0.19, _shade(c, 0.90), d, r=0.03),
        _ellipse(0.44, 0.47, 0.30, 0.185, c, d),                # body
        _curve([(0.17, 0.41), (0.115, 0.50), (0.13, 0.60)], d, 0.012),  # tail
        _rect(0.31, 0.575, 0.11, 0.20, _shade(c, 1.04), d, r=0.03),   # near legs
        _rect(0.62, 0.575, 0.11, 0.20, _shade(c, 1.04), d, r=0.03),
        _ellipse(0.735, 0.375, 0.135, 0.125, _shade(c, 1.02), d),     # head
        _ellipse(0.660, 0.375, 0.082, 0.105, _shade(c, 0.93), d),     # ear
        _curve([(0.815, 0.44), (0.855, 0.55), (0.845, 0.655),
                (0.795, 0.725), (0.765, 0.715)], c, 0.050),     # trunk
        _poly([(0.787, 0.470), (0.812, 0.472), (0.800, 0.545)], "#f6f1e4", d, 0.004),
        _circle(0.795, 0.345, 0.018, "#20262e"),                # eye
        _curve([(0.755, 0.305), (0.785, 0.290), (0.820, 0.310)], d, 0.007),  # brow
        _curve([(0.745, 0.425), (0.775, 0.455)], d, 0.006),     # mouth line
    ]


def _cat(c: str, d: str) -> list:
    return [
        _ellipse(0.44, 0.60, 0.24, 0.16, c, d),                  # body
        _curve([(0.66, 0.55), (0.74, 0.50), (0.78, 0.44)], c, 0.045),    # tail
        _circle(0.30, 0.45, 0.115, c, d),                        # head
        _poly([(0.24, 0.37), (0.235, 0.26), (0.325, 0.335)], c, d),      # ear L
        _poly([(0.365, 0.335), (0.40, 0.265), (0.395, 0.365)], c, d),    # ear R
        _ellipse(0.295, 0.455, 0.017, 0.022, "#20262e"),          # eyes
        _ellipse(0.328, 0.455, 0.017, 0.022, "#20262e"),
        _poly([(0.312, 0.485), (0.306, 0.476), (0.318, 0.476)], "#e88"),  # nose
        _curve([(0.312, 0.492), (0.30, 0.505), (0.29, 0.500)], d, 0.006),
        _curve([(0.312, 0.492), (0.325, 0.505), (0.335, 0.500)], d, 0.006),
        _curve([(0.295, 0.53), (0.312, 0.535), (0.33, 0.53)], d, 0.005),
        _rect(0.33, 0.70, 0.07, 0.14, _shade(c, 0.95), d, r=0.02),
        _rect(0.48, 0.70, 0.07, 0.14, _shade(c, 1.05), d, r=0.02),
    ]


def _dog(c: str, d: str) -> list:
    return [
        _ellipse(0.47, 0.60, 0.23, 0.15, c, d),
        _curve([(0.68, 0.52), (0.77, 0.47), (0.80, 0.40)], c, 0.035),
        _circle(0.31, 0.48, 0.115, c, d),
        _ellipse(0.245, 0.50, 0.045, 0.085, _shade(c, 0.88), d),   # floppy ear
        _ellipse(0.375, 0.50, 0.038, 0.075, _shade(c, 1.06), d),
        _ellipse(0.50, 0.475, 0.055, 0.045, c, d),                 # snout
        _circle(0.48, 0.462, 0.014, "#20262e"),                    # nose
        _circle(0.295, 0.465, 0.016, "#20262e"),
        _circle(0.335, 0.465, 0.016, "#20262e"),
        _curve([(0.45, 0.505), (0.47, 0.52), (0.50, 0.508)], d, 0.006),
        _rect(0.36, 0.70, 0.07, 0.14, _shade(c, 0.95), d, r=0.02),
        _rect(0.50, 0.70, 0.07, 0.14, _shade(c, 1.05), d, r=0.02),
    ]


def _house(c: str, d: str) -> list:
    return [
        _rect(0.28, 0.46, 0.44, 0.36, "#efe7d8", d, r=0.01),
        _poly([(0.22, 0.46), (0.50, 0.24), (0.78, 0.46)], c, d),          # roof
        _rect(0.45, 0.60, 0.11, 0.22, "#8d6b4a", d, r=0.008),             # door
        _circle(0.543, 0.715, 0.008, "#e8c26a"),
        _rect(0.32, 0.52, 0.09, 0.09, "#a8d8f0", d, r=0.005),             # window
        _rect(0.60, 0.52, 0.09, 0.09, "#a8d8f0", d, r=0.005),
        _rect(0.635, 0.32, 0.05, 0.10, _shade(c, 0.85), d, r=0.006),      # chimney
    ]


def _tree(c: str, d: str) -> list:
    return [
        _rect(0.465, 0.52, 0.075, 0.30, "#8d6b4a", d, r=0.01),
        _circle(0.50, 0.42, 0.155, c, d),
        _circle(0.405, 0.47, 0.105, _shade(c, 0.92), d),
        _circle(0.60, 0.47, 0.11, _shade(c, 1.08), d),
        _circle(0.50, 0.31, 0.105, _shade(c, 1.04), d),
    ]


def _flower(c: str, d: str) -> list:
    petals = []
    for i in range(6):
        a = i * math.pi / 3
        petals.append(_ellipse(0.5 + 0.075 * math.cos(a), 0.40 + 0.075 * math.sin(a),
                               0.055, 0.055, c, d))
    return [
        _curve([(0.5, 0.46), (0.5, 0.80)], "#5fa05f", 0.016),
        _ellipse(0.545, 0.60, 0.045, 0.022, "#6bb56b", d),
        *petals,
        _circle(0.5, 0.40, 0.045, "#f0b429", d),
    ]


def _car(c: str, d: str) -> list:
    return [
        _rect(0.20, 0.50, 0.60, 0.16, c, d, r=0.03),                      # body
        _poly([(0.32, 0.50), (0.40, 0.38), (0.60, 0.38), (0.68, 0.50)], c, d),
        _rect(0.42, 0.405, 0.075, 0.085, "#bfe4f5", d, r=0.005),
        _rect(0.515, 0.405, 0.075, 0.085, "#bfe4f5", d, r=0.005),
        _circle(0.33, 0.66, 0.055, "#2c3540", d),
        _circle(0.67, 0.66, 0.055, "#2c3540", d),
        _circle(0.33, 0.66, 0.022, "#9aa7b4"),
        _circle(0.67, 0.66, 0.022, "#9aa7b4"),
        _rect(0.79, 0.53, 0.035, 0.035, "#f5d76e", d, r=0.006),           # lamp
    ]


def _robot(c: str, d: str) -> list:
    return [
        _rect(0.36, 0.44, 0.28, 0.24, c, d, r=0.03),                      # body
        _rect(0.40, 0.26, 0.20, 0.16, c, d, r=0.025),                     # head
        _circle(0.46, 0.34, 0.022, "#38d6e8"),                            # eyes
        _circle(0.54, 0.34, 0.022, "#38d6e8"),
        _rect(0.465, 0.20, 0.07, 0.06, _shade(c, 0.9), d, r=0.006),       # antenna
        _circle(0.50, 0.185, 0.018, "#e85d5d"),
        _rect(0.28, 0.47, 0.07, 0.16, _shade(c, 0.95), d, r=0.02),        # arms
        _rect(0.65, 0.47, 0.07, 0.16, _shade(c, 1.05), d, r=0.02),
        _rect(0.40, 0.68, 0.08, 0.14, _shade(c, 0.95), d, r=0.02),        # legs
        _rect(0.52, 0.68, 0.08, 0.14, _shade(c, 1.05), d, r=0.02),
    ]


def _fish(c: str, d: str) -> list:
    return [
        _ellipse(0.50, 0.50, 0.20, 0.13, c, d),
        _poly([(0.70, 0.50), (0.82, 0.38), (0.80, 0.50), (0.82, 0.62)], _shade(c, 0.9), d),
        _circle(0.36, 0.47, 0.016, "#20262e"),
        _curve([(0.42, 0.55), (0.47, 0.58), (0.52, 0.55)], d, 0.006),
        _poly([(0.50, 0.38), (0.56, 0.30), (0.60, 0.40)], _shade(c, 1.08), d),
    ]


def _sun(c: str, d: str) -> list:
    rays = []
    for i in range(12):
        a = i * math.pi / 6
        rays.append(_curve([(0.5 + 0.16 * math.cos(a), 0.5 + 0.16 * math.sin(a)),
                            (0.5 + 0.24 * math.cos(a), 0.5 + 0.24 * math.sin(a))],
                           c, 0.018))
    return [_circle(0.5, 0.5, 0.125, c, d), *rays]


PAINTERS = {
    "elephant": _elephant, "cat": _cat, "dog": _dog, "house": _house,
    "tree": _tree, "flower": _flower, "car": _car, "robot": _robot,
    "fish": _fish, "sun": _sun,
}


def _shade(hex_colour: str, factor: float) -> str:
    """Lighten (>1) or darken (<1) a hex colour. Keeps the sketch readable."""
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return hex_colour
    f = max(0.2, min(1.8, factor))
    r, g, b = (max(0, min(255, int(v * f))) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# ----------------------------------------------------------------- document
@dataclass
class Sketch:
    """A drawing you can talk to. Everything here is reversible."""
    subject: str = "elephant"
    accent: str = "#9aa7b4"
    scale: float = 1.0
    dx: float = 0.0
    dy: float = 0.0
    rotate: float = 0.0
    extras: list[str] = field(default_factory=list)
    title: str = ""
    history: list[dict] = field(default_factory=list)

    # -- state ---------------------------------------------------------
    def snapshot(self) -> dict:
        return {"subject": self.subject, "accent": self.accent, "scale": self.scale,
                "dx": self.dx, "dy": self.dy, "rotate": self.rotate,
                "extras": list(self.extras), "title": self.title}

    def restore(self, snap: dict) -> None:
        self.subject = snap["subject"]
        self.accent = snap["accent"]
        self.scale = snap["scale"]
        self.dx = snap["dx"]
        self.dy = snap["dy"]
        self.rotate = snap["rotate"]
        self.extras = list(snap["extras"])
        self.title = snap["title"]

    def push(self) -> None:
        self.history.append(self.snapshot())
        del self.history[:-24]

    def undo(self) -> bool:
        if not self.history:
            return False
        self.restore(self.history.pop())
        return True

    # -- rendering -----------------------------------------------------
    def render(self, width: int = 900, height: int = 640, background: bool = True):
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter,
                                   QPainterPath, QPen)

        img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("#0b1220"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if background:
            g = QLinearGradient(0, 0, 0, height)
            g.setColorAt(0.0, QColor("#0a1524"))
            g.setColorAt(0.72, QColor("#10233a"))
            g.setColorAt(1.0, QColor("#0a1420"))
            p.fillRect(0, 0, width, height, QBrush(g))
            p.setPen(QPen(QColor(34, 211, 238, 38), 1))
            p.drawLine(0, int(height * 0.84), width, int(height * 0.84))

        dark = "#18202b"
        side = min(width, height)

        # decorations first, in canvas space — they are scenery, not part of the
        # subject, so moving or scaling the subject must not drag them along
        for ex in self.extras:
            slot = {"sun": (0.14, 0.16), "cloud": (0.32, 0.13), "tree": (0.855, 0.62),
                    "flower": (0.13, 0.74), "star": (0.80, 0.15)}.get(ex)
            if slot is None:
                continue
            p.save()
            p.translate(width * slot[0], height * slot[1])
            size = side * 0.20
            p.scale(size, size)
            p.translate(-0.5, -0.5)
            for prim in _paint_extras(ex, self.accent):
                _draw(p, prim, QPointF, QRectF, QPainterPath, QColor, QPen, QBrush, Qt)
            p.restore()

        p.save()
        p.translate(width / 2 + self.dx * width, height * 0.52 + self.dy * height)
        p.rotate(self.rotate)
        p.scale(side * 0.95 * self.scale, side * 0.95 * self.scale)
        p.translate(-0.5, -0.5)

        painter = PAINTERS.get(self.subject, _elephant)
        for prim in painter(self.accent, dark):
            _draw(p, prim, QPointF, QRectF, QPainterPath, QColor, QPen, QBrush, Qt)
        p.restore()
        p.end()
        return img

    # -- language ------------------------------------------------------
    def apply(self, text: str) -> tuple[bool, str]:
        """Mutate the sketch from a sentence. Returns (changed, human reply)."""
        low = (text or "").lower().strip()
        if not low:
            return False, "Nothing to change."

        # undo / clear first: they are unambiguous
        if re.search(r"\b(undo|revert|go back)\b", low):
            return (self.undo(), "undone" if self.history else "nothing to undo")
        if re.search(r"\b(clear|erase everything|start over|blank)\b", low):
            self.push()
            self.extras.clear()
            self.scale, self.dx, self.dy, self.rotate = 1.0, 0.0, 0.0, 0.0
            return True, "cleared the extras and transforms"

        changed = False
        notes: list[str] = []

        # A new subject only when it is grammatically the object of a drawing
        # verb ("draw a cat", "make it into a house"). An earlier version keyed
        # on the bare word plus "make", so "make it purple, add a sun" replaced
        # the elephant with a sun — which is exactly the kind of bug that makes
        # an assistant feel stupid.
        new_subject = ""
        # the article must be followed by whitespace, otherwise "an elephant"
        # is parsed as article="an" + subject="" and the word is lost
        m = re.search(r"\b(draw|sketch|paint|render|create)\s+(?:me\s+)?"
                      r"(?:an?\s+|the\s+|a\s+)?([a-z]+)", low)
        if m and m.group(2) in ALIAS:
            new_subject = ALIAS[m.group(2)]
        else:
            m = re.search(r"\b(?:make|turn)\s+it\s+(?:in)?to\s+(?:an?\s+|a\s+)?([a-z]+)",
                          low)
            if m and m.group(1) in ALIAS:
                new_subject = ALIAS[m.group(1)]
        if new_subject and new_subject != self.subject:
            self.push()
            self.subject = new_subject
            self.title = new_subject
            changed = True
            notes.append(f"now drawing a {new_subject}")

        for name, hexv in PALETTE.items():
            if re.search(rf"\b{name}\b", low):
                self.push() if not changed else None
                self.accent = hexv
                changed = True
                notes.append(f"colour → {name}")
                break

        if re.search(r"\b(bigger|larger|zoom in|grow|enlarge)\b", low):
            self.push(); self.scale = min(1.9, self.scale * 1.22)
            changed = True; notes.append(f"scale → {self.scale:.2f}×")
        if re.search(r"\b(smaller|tiny|zoom out|shrink|reduce)\b", low):
            self.push(); self.scale = max(0.42, self.scale / 1.22)
            changed = True; notes.append(f"scale → {self.scale:.2f}×")
        if re.search(r"\b(left)\b", low):
            self.push(); self.dx = max(-0.35, self.dx - 0.06)
            changed = True; notes.append("moved left")
        if re.search(r"\b(right)\b", low):
            self.push(); self.dx = min(0.35, self.dx + 0.06)
            changed = True; notes.append("moved right")
        if re.search(r"\b(up|higher|raise)\b", low):
            self.push(); self.dy = max(-0.30, self.dy - 0.05)
            changed = True; notes.append("moved up")
        if re.search(r"\b(down|lower)\b", low):
            self.push(); self.dy = min(0.30, self.dy + 0.05)
            changed = True; notes.append("moved down")
        if re.search(r"\b(rotate|tilt|slant)\b", low):
            self.push(); self.rotate = (self.rotate - 12) % 360
            changed = True; notes.append(f"rotated to {self.rotate:.0f}°")

        for extra in ("sun", "cloud", "tree", "flower", "star"):
            if re.search(rf"\b(add|with|include)\b.*\b{extra}\b", low) and extra not in self.extras:
                self.push(); self.extras.append(extra)
                changed = True; notes.append(f"added a {extra}")
            elif re.search(rf"\b(remove|delete|without|no)\b.*\b{extra}\b", low) \
                    and extra in self.extras:
                self.push(); self.extras.remove(extra)
                changed = True; notes.append(f"removed the {extra}")

        if not changed:
            return False, ("I can change: colour (say 'make it purple'), size (bigger/smaller), "
                           "position (left/right/up/down), rotation, extras (add a sun), "
                           "or draw a different thing.")
        return True, ", ".join(notes)


def _paint_extras(name: str, accent: str) -> list:
    if name == "cloud":
        return [_ellipse(0.46, 0.52, 0.16, 0.09, "#cfdae6"),
                _ellipse(0.60, 0.50, 0.12, 0.075, "#cfdae6"),
                _ellipse(0.34, 0.50, 0.11, 0.07, "#cfdae6")]
    if name == "star":
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            r = 0.22 if i % 2 == 0 else 0.09
            pts.append((0.5 + r * math.cos(a), 0.5 + r * math.sin(a)))
        return [_poly(pts, "#f5d76e", "#a9862a", 0.005)]
    painter = PAINTERS.get(name)
    return painter(accent, "#18202b") if painter else []


def _draw(p, prim, QPointF, QRectF, QPainterPath, QColor, QPen, QBrush, Qt):  # noqa: N803
    """Render one primitive. Coordinates are 0..1; QPainter is already scaled."""
    kind = prim[0]
    if kind == "ellipse":
        _, cx, cy, rx, ry, fill, line, lw = prim
        p.setBrush(QBrush(QColor(fill)))
        p.setPen(QPen(QColor(line), lw) if line else Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))
    elif kind == "rect":
        _, x, y, w, h, fill, line, lw, r = prim
        p.setBrush(QBrush(QColor(fill)))
        p.setPen(QPen(QColor(line), lw) if line else Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(x, y, w, h), r, r)
    elif kind == "poly":
        _, pts, fill, line, lw = prim
        path = QPainterPath()
        path.moveTo(QPointF(pts[0][0], pts[0][1]))
        for x, y in pts[1:]:
            path.lineTo(QPointF(x, y))
        path.closeSubpath()
        p.setBrush(QBrush(QColor(fill)))
        p.setPen(QPen(QColor(line), lw) if line else Qt.PenStyle.NoPen)
        p.drawPath(path)
    elif kind == "curve":
        _, pts, stroke, lw, fill = prim
        path = QPainterPath()
        path.moveTo(QPointF(pts[0][0], pts[0][1]))
        for i in range(1, len(pts)):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            path.quadTo(QPointF(x0, y0), QPointF(cx, cy))
        p.setBrush(QBrush(QColor(fill)) if fill else Qt.BrushStyle.NoBrush)
        pen = QPen(QColor(stroke), lw)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)


# ------------------------------------------------------------------ saving
def art_dir() -> Path:
    d = Path.home() / "Pictures" / "ArcArt"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:
        from . import config
        d = config.data_dir() / "art"
        d.mkdir(parents=True, exist_ok=True)
        return d


def save_sketch(sketch: Sketch, path: str = "", width: int = 1400, height: int = 1000) -> str:
    """Never overwrites: a new timestamped file every time."""
    img = sketch.render(width, height)
    if path:
        target = Path(path).expanduser()
        if target.is_dir():
            target = target / f"arc_{sketch.subject}_{int(time.time())}.png"
    else:
        target = art_dir() / f"arc_{sketch.subject}_{int(time.time())}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():                    # never clobber an earlier version
        stem, i = target.stem, 2
        while True:
            cand = target.with_name(f"{stem}_v{i}{target.suffix}")
            if not cand.exists():
                target = cand
                break
            i += 1
    img.save(str(target), "PNG")
    return str(target)


# ------------------------------------------------- real image models, if any
IMAGE_BACKENDS = (
    ("comfyui", "ComfyUI", "comfyanonymous/ComfyUI", 8188),
    ("a1111", "Stable Diffusion WebUI", "AUTOMATIC1111/stable-diffusion-webui", 7860),
    ("fooocus", "Fooocus", "lllyasviel/Fooocus", 7865),
    ("invokeai", "InvokeAI", "invoke-ai/InvokeAI", 9090),
)


def image_backends() -> list[tuple[str, str, str, int]]:
    """Which local image models are listening? Same 250 ms probe as the brains."""
    import socket
    found = []
    for key, label, repo, port in IMAGE_BACKENDS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                found.append((key, label, repo, port))
        except OSError:
            continue
    return found
