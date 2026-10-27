"""The JARVIS Core — hand-painted reactor, zero image assets.

The whole file is a CPU-budget exercise. Three layers:

  1. STATIC layer  (halo, tick ring, 10 coils, inner ring)
     Rendered once into a QPixmap, re-rendered only on resize/theme change.

  2. GLOW layer    (the bright core)
     Also a cached pixmap. The breathing effect is done with painter opacity,
     NOT by rebuilding a QRadialGradient every frame. Gradient construction
     is one of the most expensive things in a software rasterizer.

  3. LIVE layer    (3 arcs + 3 orbit dots)
     The only things that actually change per frame. Dots are pre-rendered
     sprites, so a frame costs a few blits plus three drawArc calls.

Net effect: at 30 fps the reactor stays cheap, and every layer honours the
mode's effect scale, so Gaming mode is nearly free.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..theme import Theme
from ..ticker import ticker


class ArcReactor(QWidget):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._effects = theme.effects
        self._t = 0.0
        self._rot = 0.0

        self._static: QPixmap | None = None
        self._static_key: tuple | None = None
        self._glow: QPixmap | None = None
        self._glow_key: tuple | None = None
        self._dot: QPixmap | None = None
        self._dot_key: tuple | None = None

        self.setMinimumSize(240, 240)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        ticker().tick.connect(self._on_tick)

    # -- public ----------------------------------------------------------
    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._effects = theme.effects
        self._invalidate()
        self.update()

    def set_effects(self, scale: float) -> None:
        self._effects = max(0.0, min(1.0, float(scale)))
        self._invalidate()
        self.update()

    def advance(self, seconds: float) -> None:
        """Used by --screenshot so a still frame has a nice rotation."""
        self._t += seconds
        self._rot = (self._rot + seconds * 24.0) % 360.0
        self.update()

    def _invalidate(self) -> None:
        self._static_key = None
        self._glow_key = None
        self._dot_key = None

    # -- tick ------------------------------------------------------------
    def _on_tick(self, dt: float) -> None:
        self._t += dt
        self._rot = (self._rot + dt * 24.0 * (0.35 + 0.65 * self._effects)) % 360.0
        if self.isVisible():
            self.update()

    # -- cached layers ---------------------------------------------------
    def _dpr(self) -> float:
        return self.devicePixelRatioF() or 1.0

    def _static_pixmap(self) -> QPixmap:
        dpr = self._dpr()
        key = (self.width(), self.height(), round(dpr, 2), self._theme.key,
               round(self._effects, 2))
        if self._static is not None and self._static_key == key:
            return self._static

        w, h = max(1, self.width()), max(1, self.height())
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)

        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = QPointF(w / 2.0, h / 2.0)
        R = min(w, h) / 2.0 - 6.0
        eff = self._effects
        accent = self._theme.q("accent")
        accent2 = self._theme.q("accent2")

        def mix(alpha: float) -> QColor:
            return QColor(accent.red(), accent.green(), accent.blue(),
                          max(0, min(255, int(alpha))))

        # outer halo
        grad = QRadialGradient(c, R * 1.02)
        grad.setColorAt(0.00, mix(74 * eff))
        grad.setColorAt(0.55, mix(26 * eff))
        grad.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(c, R * 1.02, R * 1.02)

        # outer ring
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(mix(110), max(1.0, R * 0.010)))
        p.drawEllipse(c, R * 0.965, R * 0.965)

        # tick ring
        for i in range(72):
            ang = math.radians(i * 5.0 - 90.0)
            major = (i % 6 == 0)
            r1, r2 = R * 0.925, R * (0.865 if major else 0.895)
            p.setPen(QPen(mix((150 if major else 62) * eff),
                          max(1.0, R * (0.012 if major else 0.007))))
            p.drawLine(QPointF(c.x() + math.cos(ang) * r1, c.y() + math.sin(ang) * r1),
                       QPointF(c.x() + math.cos(ang) * r2, c.y() + math.sin(ang) * r2))

        # coils
        p.save()
        p.translate(c)
        coil_pen = QPen(QColor(accent2.red(), accent2.green(), accent2.blue(),
                               int(70 * eff)), 1.0)
        coil_brush = QColor(accent2.red(), accent2.green(), accent2.blue(), int(46 * eff))
        for i in range(10):
            p.save()
            p.rotate(i * 36.0)
            p.setPen(coil_pen)
            p.setBrush(coil_brush)
            p.drawRoundedRect(QRectF(-R * 0.062, -R * 0.795, R * 0.124, R * 0.185),
                              R * 0.030, R * 0.030)
            p.restore()
        p.restore()

        # inner ring
        p.setPen(QPen(mix(60 * eff), max(1.0, R * 0.006)))
        p.drawEllipse(c, R * 0.70, R * 0.70)
        p.end()

        self._static = pm
        self._static_key = key
        return pm

    def _glow_pixmap(self, box: int) -> QPixmap:
        dpr = self._dpr()
        key = (box, round(dpr, 2), self._theme.key, round(self._effects, 2))
        if self._glow is not None and self._glow_key == key:
            return self._glow

        accent = self._theme.q("accent")
        eff = self._effects
        pm = QPixmap(int(box * dpr), int(box * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = QPointF(box / 2.0, box / 2.0)
        r = box / 2.0
        grad = QRadialGradient(c, r)
        grad.setColorAt(0.00, QColor(255, 255, 255, 240))
        grad.setColorAt(0.20, QColor(accent.red(), accent.green(), accent.blue(), 225))
        grad.setColorAt(0.55, QColor(accent.red(), accent.green(), accent.blue(),
                                     int(105 * eff)))
        grad.setColorAt(1.00, QColor(accent.red(), accent.green(), accent.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(c, r, r)
        p.end()
        self._glow = pm
        self._glow_key = key
        return pm

    def _dot_pixmap(self, size: int) -> QPixmap:
        dpr = self._dpr()
        key = (size, round(dpr, 2), self._theme.key)
        if self._dot is not None and self._dot_key == key:
            return self._dot
        accent2 = self._theme.q("accent2")
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = QPointF(size / 2.0, size / 2.0)
        grad = QRadialGradient(c, size / 2.0)
        grad.setColorAt(0.00, QColor(255, 255, 255, 235))
        grad.setColorAt(0.22, QColor(accent2.red(), accent2.green(), accent2.blue(), 235))
        grad.setColorAt(1.00, QColor(accent2.red(), accent2.green(), accent2.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(c, size / 2.0, size / 2.0)
        p.end()
        self._dot = pm
        self._dot_key = key
        return pm

    # -- paint -----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            return
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        q.drawPixmap(0, 0, self._static_pixmap())

        c = QPointF(w / 2.0, h / 2.0)
        R = min(w, h) / 2.0 - 6.0
        eff = self._effects
        accent = self._theme.q("accent")
        accent2 = self._theme.q("accent2")

        # core glow: cached blit, breathing via opacity only
        glow_box = int(R * 0.94)
        pulse = 1.0 + 0.06 * math.sin(self._t * 2.2) * eff
        q.setOpacity(max(0.15, min(1.0, 0.72 + 0.22 * math.sin(self._t * 2.2) * eff)))
        gp = self._glow_pixmap(glow_box)
        gsz = glow_box * pulse
        q.drawPixmap(QRectF(c.x() - gsz / 2, c.y() - gsz / 2, gsz, gsz), gp,
                     QRectF(0, 0, gp.width(), gp.height()))
        q.setOpacity(1.0)

        if eff <= 0.0:
            q.end()
            return

        # rotating arcs
        track = QRectF(c.x() - R * 0.83, c.y() - R * 0.83, R * 1.66, R * 1.66)
        arcs = (
            (74.0, 0.0, 0.048, accent, 1.00),
            (48.0, 132.0, 0.030, accent2, -1.35),
            (24.0, 248.0, 0.020, accent, 2.10),
        )
        for span, off, widthf, col, dirn in arcs:
            q.setPen(QPen(QColor(col.red(), col.green(), col.blue(), int(235)),
                          max(1.5, R * widthf),
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            q.drawArc(track, int((self._rot * dirn + off) * 16), int(span * 16))

        # orbit dots: cached sprite
        dot = self._dot_pixmap(max(12, int(R * 0.135)))
        ds = dot.width() / dot.devicePixelRatio()
        for i in range(3):
            ang = math.radians(self._rot * 1.9 + i * 120.0)
            pt = QPointF(c.x() + math.cos(ang) * R * 0.60,
                         c.y() + math.sin(ang) * R * 0.60)
            q.drawPixmap(QRectF(pt.x() - ds / 2, pt.y() - ds / 2, ds, ds), dot,
                         QRectF(0, 0, dot.width(), dot.height()))

        q.end()
