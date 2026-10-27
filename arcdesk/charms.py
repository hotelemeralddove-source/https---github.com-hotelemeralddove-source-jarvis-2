"""Gravity Charms — floating objects that live on your desktop.

This is the feature that could have wrecked the performance budget, so it is
built around four hard rules:

1. NOTHING IS A 3D ENGINE.
   Charms are painted sprites (a few hundred bytes of QPainter code each) with
   slow 3D-ish motion: drift, bob, spin, parallax by scale. A real 3D layer would
   mean WebEngine/OpenGL (100 MB+) for something that should look like a toy
   floating on your wallpaper.

2. ONE TRANSPARENT WINDOW, CLICK-THROUGH BY DEFAULT.
   The overlay ignores the mouse entirely unless you turn on edit mode, so it can
   never block your icons, your taskbar or your work.

3. EVERYTHING IS CAPPED.
   Max 8 charms, 20 fps, and the whole overlay hides itself in Gaming mode or
   when animations are paused. Sprites are cached per (kind, size, theme).

4. POSITIONS ARE THE ONLY STATE.
   `{kind, x, y, scale, speed}` per charm, saved to settings.json. No timers per
   charm, no threads, no per-frame allocation.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QGuiApplication, QPainter, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import QMenu, QWidget

from .theme import Theme
from .ticker import ticker

KINDS = ("bot", "planet", "car", "butterfly", "reactor")
MAX_CHARMS = 8
BASE = 96          # sprite base size in px
OVERLAY_FPS = 20   # hard cap for the overlay, independent of the app mode


@dataclass
class Charm:
    kind: str = "bot"
    x: float = 120.0        # screen coords, top-left of the sprite box
    y: float = 120.0
    scale: float = 1.0      # 0.5 - 2.0
    speed: float = 1.0      # 0.2 - 3.0
    phase: float = field(default_factory=lambda: random.random() * math.tau)

    def size(self) -> int:
        return int(BASE * max(0.35, min(2.2, self.scale)))

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Charm":
        kind = str(d.get("kind", "bot"))
        return cls(
            kind=kind if kind in KINDS else "bot",
            x=float(d.get("x", 120)), y=float(d.get("y", 120)),
            scale=max(0.35, min(2.2, float(d.get("scale", 1.0)))),
            speed=max(0.2, min(3.0, float(d.get("speed", 1.0)))),
            phase=float(d.get("phase", random.random() * math.tau)),
        )


# --------------------------------------------------------------- painting
def _accent(th: Theme) -> QColor:
    return th.q("accent")


def _accent2(th: Theme) -> QColor:
    return th.q("accent2")


def draw_sprite(kind: str, size: int, th: Theme) -> QPixmap:
    """Paint one charm into a transparent pixmap. Called only when the cache misses."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    q = QPainter(pm)
    q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 96.0                    # everything below is authored at 96 px
    a, a2 = _accent(th), _accent2(th)

    def col(c: QColor, alpha: int) -> QColor:
        return QColor(c.red(), c.green(), c.blue(), alpha)

    if kind == "bot":
        c = QPointF(size / 2, size / 2)
        glow = QRadialGradient(c, 40 * s)
        glow.setColorAt(0.0, col(a, 90))
        glow.setColorAt(1.0, col(a, 0))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(glow)
        q.drawEllipse(c, 40 * s, 40 * s)
        q.setBrush(QColor(th.panel).lighter(140))
        q.setPen(QPen(col(a, 200), max(1.0, 1.4 * s)))
        q.drawRoundedRect(QRectF(size / 2 - 21 * s, size / 2 - 19 * s, 42 * s, 38 * s),
                          12 * s, 12 * s)
        q.setPen(QPen(col(a, 190), 1.3 * s))
        q.drawLine(QPointF(size / 2, size / 2 - 19 * s), QPointF(size / 2, size / 2 - 30 * s))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(255, 255, 255, 235))
        for dx in (-8, 8):
            q.drawEllipse(QPointF(size / 2 + dx * s, size / 2 - 6 * s), 3.6 * s, 3.6 * s)
        q.setPen(QPen(col(a2, 190), 1.4 * s))
        q.drawArc(QRectF(size / 2 - 7 * s, size / 2 + 3 * s, 14 * s, 9 * s),
                  200 * 16, 140 * 16)

    elif kind == "planet":
        c = QPointF(size / 2, size / 2)
        body = QRadialGradient(QPointF(size / 2 - 8 * s, size / 2 - 8 * s), 30 * s)
        body.setColorAt(0.0, col(a.lighter(150), 245))
        body.setColorAt(0.65, col(a, 215))
        body.setColorAt(1.0, col(a.darker(220), 235))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(body)
        q.drawEllipse(c, 24 * s, 24 * s)
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.setPen(QPen(col(a2, 210), 3.2 * s))
        q.save()
        q.translate(c)
        q.rotate(-18)
        q.drawEllipse(QRectF(-38 * s, -10 * s, 76 * s, 20 * s))
        q.restore()

    elif kind == "car":
        c = QPointF(size / 2, size / 2)
        glow = QRadialGradient(c, 42 * s)
        glow.setColorAt(0.0, col(a2, 60))
        glow.setColorAt(1.0, col(a2, 0))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(glow)
        q.drawEllipse(c, 42 * s, 42 * s)
        q.setBrush(col(a, 225))
        body = QRectF(size / 2 - 34 * s, size / 2 - 4 * s, 68 * s, 18 * s)
        q.drawRoundedRect(body, 7 * s, 7 * s)
        q.setBrush(col(a.lighter(135), 235))
        q.drawRoundedRect(QRectF(size / 2 - 20 * s, size / 2 - 18 * s, 36 * s, 16 * s),
                          6 * s, 6 * s)
        q.setBrush(QColor(8, 14, 22, 240))
        for dx in (-19, 19):
            q.drawEllipse(QPointF(size / 2 + dx * s, size / 2 + 15 * s), 7 * s, 7 * s)
        q.setBrush(col(a2, 230))
        for dx in (30,):
            q.drawRoundedRect(QRectF(size / 2 + dx * s - 3 * s, size / 2 - 1 * s,
                                     6 * s, 5 * s), 2 * s, 2 * s)

    elif kind == "butterfly":
        c = QPointF(size / 2, size / 2)
        # four wings: upper pair bigger and swept, lower pair smaller
        wings = (
            (-1, 22 * s, 20 * s, -30), (1, 22 * s, 20 * s, 30),
            (-1, 16 * s, 13 * s, 38), (1, 16 * s, 13 * s, -38),
        )
        for sx, ww, hh, rot in wings:
            q.save()
            q.translate(c.x() + sx * 3 * s, c.y() + (-6 * s if hh > 16 * s else 8 * s))
            q.rotate(rot)
            wing = QRectF(sx * 2 * s if sx > 0 else -ww - 2 * s, -hh, ww, hh * 1.7)
            grad = QRadialGradient(wing.center(), max(wing.width(), wing.height()) * 0.9)
            grad.setColorAt(0.0, col(a.lighter(125), 235))
            grad.setColorAt(0.7, col(a, 190))
            grad.setColorAt(1.0, col(a2, 150))
            q.setBrush(grad)
            q.setPen(QPen(col(a2, 210), 1.1 * s))
            q.drawEllipse(wing)
            q.restore()
        # body + antennae
        q.setPen(QPen(col(a2, 60), 0))
        q.setBrush(QColor(14, 22, 32, 240))
        q.drawRoundedRect(QRectF(c.x() - 2.4 * s, c.y() - 17 * s, 4.8 * s, 35 * s),
                          2.2 * s, 2.2 * s)
        q.setPen(QPen(col(a2, 220), 1.2 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        q.drawLine(QPointF(c.x() - 1 * s, c.y() - 17 * s),
                   QPointF(c.x() - 6 * s, c.y() - 25 * s))
        q.drawLine(QPointF(c.x() + 1 * s, c.y() - 17 * s),
                   QPointF(c.x() + 6 * s, c.y() - 25 * s))

    else:  # reactor
        c = QPointF(size / 2, size / 2)
        glow = QRadialGradient(c, 40 * s)
        glow.setColorAt(0.0, QColor(255, 255, 255, 210))
        glow.setColorAt(0.35, col(a, 170))
        glow.setColorAt(1.0, col(a, 0))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(glow)
        q.drawEllipse(c, 40 * s, 40 * s)
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.setPen(QPen(col(a, 220), 2.4 * s))
        q.drawEllipse(c, 26 * s, 26 * s)
        q.setPen(QPen(col(a2, 230), 2.0 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(3):
            start = int(i * 120 * 16)
            q.drawArc(QRectF(c.x() - 19 * s, c.y() - 19 * s, 38 * s, 38 * s), start, 70 * 16)

    q.end()
    return pm


# ----------------------------------------------------------------- overlay
class CharmsOverlay(QWidget):
    changed = Signal()                  # positions changed -> save settings
    edit_mode_changed = Signal(bool)

    def __init__(self, theme: Theme, charms: list[Charm]) -> None:
        super().__init__()
        self._theme = theme
        self.charms = charms or []
        self._t = 0.0
        self._edit = False
        self._drag_index: int | None = None
        self._drag_off = QPoint(0, 0)
        self._cache: dict[tuple, QPixmap] = {}
        self._attr_applied = False
        self._since_paint = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._fit_screen()
        self.clamp_all()
        ticker().tick.connect(self._on_tick)

    # -- geometry --------------------------------------------------------
    def _fit_screen(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            self.setGeometry(0, 0, 1280, 720)
            return
        geo = screens[0].geometry()
        for s in screens[1:]:
            geo = geo.united(s.geometry())
        self.setGeometry(geo)

    def reflow(self) -> None:
        self._fit_screen()
        self.clamp_all()
        self.update()

    def clamp_all(self) -> None:
        """Default positions are authored for a wide screen; a laptop is not that
        wide, so pull any charm that would sit off-display back onto the screen."""
        geo = self.geometry()
        margin = 12
        for ch in self.charms:
            size = ch.size()
            max_x = max(margin, geo.width() - size - margin)
            max_y = max(margin, geo.height() - size - 56)   # keep clear of the taskbar
            ch.x = min(max(float(margin), ch.x), float(max_x))
            ch.y = min(max(float(margin), ch.y), float(max_y))

    # -- state -----------------------------------------------------------
    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._cache.clear()
        self.update()

    def set_edit(self, on: bool) -> None:
        if on == self._edit:
            return
        self._edit = on
        # Re-create the window flags: Qt caches input transparency, so simply
        # toggling the attribute is not reliable on Windows.
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, not on)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not on)
        self.setCursor(Qt.CursorShape.OpenHandCursor if on else Qt.CursorShape.ArrowCursor)
        if self.isVisible():
            self.hide()
            self.show()
        self.edit_mode_changed.emit(on)
        self.update()

    @property
    def editing(self) -> bool:
        return self._edit

    def set_charms(self, charms: list[Charm]) -> None:
        self.charms = charms[:MAX_CHARMS]
        self.clamp_all()
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        # screen resolution can change between sessions (dock/undock, 4K monitor)
        self.reflow()
        super().showEvent(event)

    def add_charm(self, kind: str = "bot", at: QPoint | None = None) -> Charm | None:
        if len(self.charms) >= MAX_CHARMS:
            return None
        geo = self.geometry()
        pos = at or QPoint(geo.width() // 2 - BASE // 2 + random.randint(-160, 160),
                           geo.height() // 3 + random.randint(-80, 160))
        ch = Charm(kind=kind, x=float(pos.x()), y=float(pos.y()))
        self.charms.append(ch)
        self.update()
        self.changed.emit()
        return ch

    def remove_last(self) -> None:
        if self.charms:
            self.charms.pop()
            self.update()
            self.changed.emit()

    def dump(self) -> list[dict]:
        return [c.as_dict() for c in self.charms]

    # -- animation -------------------------------------------------------
    def _on_tick(self, dt: float) -> None:
        """Advance time every tick, but repaint at most OVERLAY_FPS times a second.

        The shared ticker may run at 30 fps for the main window; a full-screen
        overlay does not need that, and skipping the extra paint is what keeps the
        charms at ~1 % CPU.
        """
        if not self.isVisible():
            return
        self._t += dt
        self._since_paint += dt
        if self._since_paint * OVERLAY_FPS >= 1.0:
            self._since_paint = 0.0
            self.update()

    def advance(self, seconds: float) -> None:
        self._t += seconds
        self.update()

    # -- paint -----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        if not self.charms:
            return
        th = self._theme
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        for ch in self.charms:
            depth = max(0.35, min(2.2, ch.scale)) / 2.2       # parallax factor
            sp = max(0.2, ch.speed)
            t = self._t * sp
            # slow lissajous drift + bob; nothing loops fast enough to distract
            dx = math.sin(t * 0.33 + ch.phase) * (26 + 30 * depth)
            dy = math.cos(t * 0.27 + ch.phase * 1.7) * (14 + 20 * depth)
            tilt = math.sin(t * 0.5 + ch.phase) * 7.0

            size = ch.size()
            key = (ch.kind, size, th.key)
            pix = self._cache.get(key)
            if pix is None:
                pix = draw_sprite(ch.kind, size, th)
                self._cache[key] = pix

            x = ch.x + dx
            y = ch.y + dy
            q.save()
            q.translate(x + size / 2.0, y + size / 2.0)
            q.rotate(tilt)
            alpha = 0.72 + 0.28 * depth
            q.setOpacity(alpha)
            q.drawPixmap(QPointF(-size / 2.0, -size / 2.0), pix)
            q.setOpacity(1.0)
            if self._edit:
                q.setPen(QPen(QColor(th.accent), 1.0, Qt.PenStyle.DashLine))
                q.setBrush(Qt.BrushStyle.NoBrush)
                q.drawRect(QRectF(-size / 2.0, -size / 2.0, size, size))
            q.restore()
        q.end()

    # -- interaction (edit mode only) ------------------------------------
    def _hit(self, pos: QPoint) -> int | None:
        for i in range(len(self.charms) - 1, -1, -1):
            ch = self.charms[i]
            size = ch.size()
            if QRectF(ch.x, ch.y, size, size).contains(QPointF(pos)):
                return i
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._edit:
            return
        idx = self._hit(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and idx is not None:
            self._drag_index = idx
            self._drag_off = event.position().toPoint() - QPoint(int(self.charms[idx].x),
                                                                 int(self.charms[idx].y))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.RightButton:
            self._context_menu(event.position().toPoint(), idx)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_index is None or not self._edit:
            return
        p = event.position().toPoint() - self._drag_off
        ch = self.charms[self._drag_index]
        ch.x, ch.y = float(p.x()), float(p.y())
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_index is not None:
            self._drag_index = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.changed.emit()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self._edit:
            return
        idx = self._hit(event.position().toPoint())
        if idx is None:
            return
        step = 0.08 if event.angleDelta().y() > 0 else -0.08
        ch = self.charms[idx]
        ch.scale = max(0.35, min(2.2, ch.scale + step))
        self.update()
        self.changed.emit()

    def _context_menu(self, pos: QPoint, idx: int | None) -> None:
        m = QMenu(self)
        if idx is not None:
            ch = self.charms[idx]
            m.addAction(f"{ch.kind.upper()}  ·  speed {ch.speed:.1f}×").setEnabled(False)
            m.addSeparator()
            for k in KINDS:
                act = m.addAction(f"change to {k}")
                act.triggered.connect(lambda _=False, i=idx, kind=k: self._set_kind(i, kind))
            faster = m.addAction("faster")
            faster.triggered.connect(lambda: self._bump_speed(idx, +0.3))
            slower = m.addAction("slower")
            slower.triggered.connect(lambda: self._bump_speed(idx, -0.3))
            m.addSeparator()
            m.addAction("remove this charm").triggered.connect(
                lambda: self._remove(idx))
            m.addSeparator()
        for k in KINDS:
            m.addAction(f"add {k}").triggered.connect(
                lambda _=False, kind=k: self.add_charm(kind, pos))
        m.addAction("exit edit mode").triggered.connect(lambda: self.set_edit(False))
        m.exec(self.mapToGlobal(pos))

    def _set_kind(self, idx: int, kind: str) -> None:
        self.charms[idx].kind = kind
        self.update()
        self.changed.emit()

    def _bump_speed(self, idx: int, delta: float) -> None:
        ch = self.charms[idx]
        ch.speed = max(0.2, min(3.0, ch.speed + delta))
        self.changed.emit()

    def _remove(self, idx: int) -> None:
        try:
            self.charms.pop(idx)
        except IndexError:
            return
        self.update()
        self.changed.emit()
