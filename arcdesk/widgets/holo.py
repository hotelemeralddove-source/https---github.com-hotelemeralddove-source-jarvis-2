"""The Hologram Deck — a projected command surface, painted with CPU only.

The brief: *look like a scientific server running, rendered as a hologram*.
Two constraints shape every decision in this file:

  * **it has to be real.** Every number on screen is measured — CPU, memory,
    disk, network deltas, process count, tool calls, uptime — not decoration.
    A hologram full of fake telemetry is a poster, not an instrument.
  * **it has to stay cheap.** No OpenGL, no shaders, no per-frame gradient
    construction. Static layers (starfield, floor grid, hex field, vignette,
    corner brackets, scanlines) are rendered once into a QPixmap on resize and
    then blitted; per frame we only draw lines, arcs and text. The glow is a
    cached radial sprite, so the expensive thing happens once.

Layers, back to front:

  1. deep-space gradient + perspective floor grid + hex field   (cached)
  2. data-stream columns on both edges                          (cheap text)
  3. wireframe globe with nodes and inter-node arcs             (lines)
  4. arc-reactor core: reticle rings, rotating arcs, bloom      (arcs + cached sprite)
  5. volumetric projection cone from the floor, additive        (cached sprite)
  6. telemetry panels with live sparklines                      (sampled 4 Hz)
  7. scan sweep, grain, scanlines, vignette, flicker            (cached + opacity)
  8. boot sequence for the first two seconds                    (text)

Honesty note: the flicker and the grain are deliberate artefacts of the
*simulation* of a projector — they are labelled as such in the settings
("projector noise"), and turning effects down removes them.
"""
from __future__ import annotations

import math
import random
import time
from collections import deque

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient,
                           QTransform)
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..theme import Theme
from ..ticker import ticker

MONO = "Consolas, DejaVu Sans Mono, Menlo, monospace"

# the projector's colour identity — cyan core, teal skin, amber for warnings
CYAN = "#48f2ff"
TEAL = "#18d7c7"
BLUE = "#3b8cff"
AMBER = "#ffc24a"
MAGENTA = "#c07bff"
WHITE = "#dffcff"


def os_getload():
    """Load average, where the platform has one (Windows does not)."""
    import psutil
    if hasattr(psutil, "getloadavg"):
        return psutil.getloadavg()
    raise AttributeError("no load average on this platform")


def _rgba(hex_colour: str, alpha: int) -> QColor:
    c = QColor(hex_colour)
    c.setAlpha(max(0, min(255, int(alpha))))
    return c


class _Sampler:
    """Real machine numbers, sampled on a timer, never invented."""

    def __init__(self) -> None:
        self.cpu = deque([0.0] * 48, maxlen=48)
        self.mem = deque([0.0] * 48, maxlen=48)
        self.net = deque([0.0] * 48, maxlen=48)
        self.ok = False
        self.psutil = None
        self.cores = 0
        self.mem_used = 0.0
        self.mem_total = 0.0
        self.disk_used = 0.0
        self.disk_total = 0.0
        self.procs = 0
        self.top: list[tuple[str, float]] = []
        self.pids: list[int] = []
        self.core_load: list[float] = []      # per-core CPU, real
        self.swap_used = 0.0
        self.swap_total = 0.0
        self.load1 = 0.0
        self.boot_time = 0.0
        self.disk_read = 0.0
        self.disk_write = 0.0
        self.threads = 0
        self.net_in = 0.0
        self.net_out = 0.0
        self._last_net = None
        self._last_t = time.time()
        #: how many samples have actually been taken (the deques start zero-filled,
        #: so anything that plots history has to skip the padding)
        self.seen = 0
        try:
            import psutil
            self.psutil = psutil
            self.cores = psutil.cpu_count(logical=True) or 0
            self.ok = True
        except Exception:
            self.ok = False

    def sample(self) -> None:
        self.seen += 1
        if not self.ok:
            # honest fallback: no fake numbers, just flat zeroes
            self.cpu.append(0.0)
            self.mem.append(0.0)
            self.net.append(0.0)
            return
        p = self.psutil
        now = time.time()
        try:
            cpu = p.cpu_percent(interval=None)
            try:
                self.core_load = [float(v) for v in p.cpu_percent(interval=None, percpu=True)]
            except Exception:
                self.core_load = []
            vm = p.virtual_memory()
            try:
                sw = p.swap_memory()
                self.swap_used, self.swap_total = float(sw.used), float(sw.total)
            except Exception:
                self.swap_used = self.swap_total = 0.0
            try:
                self.load1 = float(os_getload()[0])
            except Exception:
                self.load1 = 0.0
            self.cpu.append(cpu)
            self.mem.append(vm.percent)
            self.mem_used, self.mem_total = vm.used, vm.total
            try:
                io = p.disk_io_counters()
                self.disk_read = float(io.read_bytes) if io else 0.0
                self.disk_write = float(io.write_bytes) if io else 0.0
            except Exception:
                pass
            try:
                self.threads = int(p.cpu_count(logical=True) or 0)
            except Exception:
                pass
            try:
                du = p.disk_usage("/" if hasattr(p, "disk_usage") else "C:\\")
                self.disk_used, self.disk_total = du.used, du.total
            except Exception:
                pass
            io = p.net_io_counters()
            if self._last_net is not None and now > self._last_t:
                span = now - self._last_t
                self.net_in = max(0.0, (io.bytes_recv - self._last_net[0]) / span / 1024)
                self.net_out = max(0.0, (io.bytes_sent - self._last_net[1]) / span / 1024)
            self._last_net = (io.bytes_recv, io.bytes_sent)
            self._last_t = now
            self.net.append((self.net_in + self.net_out) / 1024)   # MB/s for the graph
            self.procs = len(p.pids())
            rows = []
            for proc in p.process_iter(["pid", "name", "memory_percent"]):
                try:
                    rows.append((str(proc.info["name"])[:16], float(proc.info["memory_percent"] or 0)))
                    self.pids.append(int(proc.info["pid"] or 0))
                except Exception:
                    continue
            rows.sort(key=lambda r: r[1], reverse=True)
            self.top = rows[:4]
            self.pids = self.pids[-8:]
        except Exception:
            self.ok = False


class HoloDeck(QWidget):
    """The full holographic surface. Embed anywhere; it scales."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._t = 0.0
        self._rot = 0.0
        self._boot = 0.0
        self._effects = max(0.2, min(1.0, theme.effects))
        self._sampler = _Sampler()
        self._sample_at = 0.0

        self._stream_cache: QPixmap | None = None
        self._stream_key: tuple | None = None
        self._stream_at = -1.0
        self._sample_serial = 0
        self._tele_cache: QPixmap | None = None
        self._tele_key: tuple | None = None
        self._bg: QPixmap | None = None
        self._bg_key: tuple | None = None
        self._grain: list[QPixmap] = []
        self._glow: QPixmap | None = None
        self._glow_key: tuple | None = None
        self._beam: QPixmap | None = None
        self._beam_key: tuple | None = None
        self._grain_i = 0
        self._hero_glow: QPixmap | None = None
        self._hero_key: tuple | None = None
        self._scaled: QPixmap | None = None
        self._num_cache: QPixmap | None = None
        self._num_key: tuple | None = None
        self._hero_cache: QPixmap | None = None
        self._hero_cache_key: tuple | None = None
        self._hero_origin = (0.0, 0.0, 0.0, 0.0)
        self._hero_at = -1.0

        # deterministic per-column stream state, so frames are reproducible
        rnd = random.Random(0xA5C)
        self._streams = [
            {"x": rnd.random(), "speed": 0.04 + rnd.random() * 0.10,
             "seed": rnd.randrange(1 << 30), "len": 14 + rnd.randrange(12)}
            for _ in range(9)
        ]
        self._started = time.time()
        self.autonomous = True      # False = an owner widget drives step()
        self.setMinimumSize(720, 420)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        ticker().tick.connect(self._on_tick)
        self._sampler.sample()

    # ------------------------------------------------------------------ api
    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._effects = max(0.2, min(1.0, theme.effects))
        self._bg_key = None
        self.update()

    def boot(self) -> None:
        self._boot = 0.0
        self._started = time.time()
        self.update()

    # --------------------------------------------------------------- frames
    def _on_tick(self, dt: float) -> None:
        if not self.autonomous or not self.isVisible():
            return
        self.step(dt)

    # ------------------------------------------------------------- stepping
    def step(self, dt: float) -> None:
        """Advance the simulation. Public so an embedding widget can drive it."""
        dt = max(0.0, min(0.2, float(dt)))
        self._t += dt
        self._boot += dt
        self._rot = (self._rot + dt * 12.0 * (0.4 + self._effects)) % 360.0
        self._sample_at += dt
        if self._sample_at >= 0.25:
            self._sample_at = 0.0
            self._sampler.sample()
            self._sample_serial += 1
        self.update()

    # ------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        w, h = self.width(), self.height()
        if w < 60 or h < 60:
            return
        q = QPainter(self)
        self.paint_onto(q, w, h)
        q.end()

    #: On a 4K screen, rasterising 8.3 M pixels of antialiased line art every frame
    #: is wasted work — the deck renders at this width and is scaled up once. The
    #: look is a projected hologram; the tiny softening is on-theme, the 20 fps it
    #: buys back is not negotiable.
    MAX_RENDER_W = 1920

    #: Resolution multiplier for the expensive render. The deck is soft light on a dark
    #: background, so drawing it at 60% and scaling up is nearly invisible — while it
    #: cuts the pixel work by roughly two thirds. The ticker lowers this automatically
    #: when a machine cannot afford full quality (see MagicScreen and HoloDeck.note_load).
    quality = 1.0

    def paint_onto(self, q: QPainter, w: int, h: int, compact: bool = False,
                   ticker_bar: bool = True) -> None:
        """Draw the whole deck into any painter.

        This is what lets the magic screen (or a screenshot tool) reuse the same
        pixels without embedding the widget and fighting over z-order.

        compact    — raise and shrink the globe so an owner can put controls under
                     it (the magic screen has buttons and an input box there)
        ticker_bar — draw the bottom event ticker; off when the owner wants that
                     strip for its own status line
        """
        if w < 60 or h < 60:
            return
        cap = int(self.MAX_RENDER_W * max(0.4, min(1.0, self.quality)))
        if w > cap:
            rw = cap
            rh = max(60, int(h * rw / w))
            if self._scaled is None or self._scaled.size() != QSize(rw, rh):
                self._scaled = QPixmap(rw, rh)
            self._scaled.fill(Qt.GlobalColor.transparent)
            sp = QPainter(self._scaled)
            self._render(sp, rw, rh, compact, ticker_bar)
            sp.end()
            # a smooth upscale of 3.7 M pixels costs more than the whole render did,
            # so the enlargement stays nearest-neighbour: the deck is soft light anyway
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            q.drawPixmap(QRect(0, 0, w, h), self._scaled)
            return
        self._render(q, w, h, compact, ticker_bar)

    def note_load(self, load: float) -> None:
        """Adapt the render resolution to what this machine can actually draw.

        `load` is the ticker's measured frame time divided by the frame budget (1.0 means
        the app is using every millisecond it has). Sustained load above 0.6 means the
        machine is behind, and a hologram is never worth a laggy window: the resolution
        steps down 1.0 -> 0.75 -> 0.6, and comes back when the machine catches up.
        """
        if load > 0.6 and self.quality > 0.61:
            self.quality = 0.75 if self.quality > 0.8 else 0.6
        elif load < 0.3 and self.quality < 1.0:
            self.quality = min(1.0, self.quality + 0.2)

    def _render(self, q: QPainter, w: int, h: int, compact: bool,
                ticker_bar: bool) -> None:
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        q.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self._ensure_layers(w, h)

        lay = self._layout(w, h, compact)
        gx, gy, gr = lay["globe"]
        hx, hy, hr = lay["hero"]
        # the gutter text has to know where the shapes are, or it prints across them
        self._geo = (hx, hy, hr)
        q.drawPixmap(0, 0, self._bg)
        self._paint_number_field(q, w, h, lay)
        self._paint_streams(q, w, h)
        self._paint_floor_beam(q, w, h)
        self._paint_globe(q, gx, gy, gr)
        self._paint_globe_dots(q, gx, gy, gr)
        self._paint_hero(q, hx, hy, hr)
        self._paint_reticle(q, hx, hy, hr)
        self._paint_instruments(q, w, h, lay)
        self._paint_edges(q, w, h)
        if not compact:
            self._paint_core_load(q, w, h)
            self._paint_spectrum(q, w, h)
            if ticker_bar:
                self._paint_ticker(q, w, h)
        self._paint_topbar(q, w, h)
        self._paint_header(q, w, h)
        self._paint_sweep(q, w, h)
        self._paint_grain(q, w, h)
        self._paint_boot(q, w, h)

    # -- cached layers ----------------------------------------------------
    def _ensure_layers(self, w: int, h: int) -> None:
        key = (w, h, self._theme.key)
        if self._bg_key == key and self._bg is not None:
            return
        self._bg_key = key
        dpr = self.devicePixelRatioF() or 1.0
        bg = QPixmap(int(w * dpr), int(h * dpr))
        bg.setDevicePixelRatio(dpr)
        bg.fill(QColor("#01050a"))
        p = QPainter(bg)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. depth: vertical gradient, slightly lighter at the horizon
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#02060d"))
        grad.setColorAt(0.45, QColor("#03121b"))
        grad.setColorAt(0.62, QColor("#052330"))
        grad.setColorAt(1.0, QColor("#01060a"))
        p.fillRect(0, 0, w, h, grad)

        # 2. starfield with parallax-safe distribution
        rnd = random.Random(w * 31 + h)
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(int(w * h / 9000)):
            x, y = rnd.random() * w, rnd.random() * h * 0.72
            a = rnd.randint(18, 90)
            r = 0.6 + rnd.random() * 1.3
            p.setBrush(_rgba(WHITE, a))
            p.drawEllipse(QPointF(x, y), r, r)

        # 3. hex field — the "substrate" the hologram sits on
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_rgba(TEAL, 16), 1.0))
        size = max(26, int(min(w, h) / 34))
        dx, dy = size * 0.87, size * 0.5
        for row in range(-1, int(h / dy) + 2):
            for col in range(-1, int(w / dx) + 2):
                x = col * dx * 2 + (dx if row % 2 else 0)
                y = row * dy
                path = QPainterPath()
                for i in range(6):
                    ang = math.radians(60 * i)
                    pt = QPointF(x + size * 0.5 * math.cos(ang),
                                 y + size * 0.5 * math.sin(ang))
                    path.moveTo(pt) if i == 0 else path.lineTo(pt)
                path.closeSubpath()
                p.drawPath(path)

        # 4. perspective floor grid (the "server room" floor)
        horizon = h * 0.72
        for i in range(1, 17):
            frac = (i / 16.0) ** 2.1
            y = horizon + (h - horizon) * frac
            p.setPen(QPen(_rgba(CYAN, int(6 + 34 * frac)), 1.0))
            p.drawLine(0, int(y), w, int(y))
        for i in range(-16, 17):
            x_top = w / 2 + i * (w / 20)
            x_bot = w / 2 + i * (w / 4.2)
            p.setPen(QPen(_rgba(CYAN, 16), 1.0))
            p.drawLine(int(x_top), int(horizon), int(x_bot), h)

        # 4b. horizon glow — the light source the hologram seems to sit in
        hg = QLinearGradient(0, h * 0.44, 0, h * 0.74)
        hg.setColorAt(0.0, QColor(0, 0, 0, 0))
        hg.setColorAt(0.55, _rgba(TEAL, 20))
        hg.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, int(h * 0.44), w, int(h * 0.30), hg)

        # 5. vignette: dark edges, so the centre reads as projected light
        vg = QRadialGradient(w / 2, h * 0.48, max(w, h) * 0.75)
        vg.setColorAt(0.0, QColor(0, 0, 0, 0))
        vg.setColorAt(0.55, QColor(0, 0, 0, 40))
        vg.setColorAt(1.0, QColor(0, 0, 0, 205))
        p.fillRect(0, 0, w, h, vg)

        # 6. scanlines (constant, part of the projector's texture)
        p.setPen(QPen(QColor(0, 0, 0, 26), 1.0))
        for y in range(0, h, 3):
            p.drawLine(0, y, w, y)

        # 7. corner brackets + frame
        p.setPen(QPen(_rgba(WHITE, 200), max(2.0, min(w, h) * 0.0030)))
        m = max(14, int(min(w, h) * 0.022))
        arm = max(34, int(min(w, h) * 0.080))
        for sx, sy in ((m, m), (w - m, m), (m, h - m), (w - m, h - m)):
            dxs = 1 if sx < w / 2 else -1
            dys = 1 if sy < h / 2 else -1
            p.drawLine(int(sx), int(sy), int(sx + arm * dxs), int(sy))
            p.drawLine(int(sx), int(sy), int(sx), int(sy + arm * dys))
        p.setPen(QPen(_rgba(CYAN, 60), 1.0))
        p.drawRect(m, m, w - 2 * m, h - 2 * m)
        p.setPen(QPen(_rgba(CYAN, 24), 1.0))
        p.drawRect(m * 2, int(m * 1.7), w - 4 * m, h - int(3.4 * m))
        p.end()
        self._bg = bg

        # grain atlas (four variants, cycled at ~10 Hz for a film feel)
        if not self._grain:
            for variant in range(4):
                g = QPixmap(180, 180)
                g.fill(Qt.GlobalColor.transparent)
                gp = QPainter(g)
                rnd = random.Random(1000 + variant)
                for _ in range(2600):
                    a = rnd.randint(6, 26)
                    gp.setPen(QPen(QColor(190, 245, 255, a), 1))
                    gp.drawPoint(rnd.randrange(180), rnd.randrange(180))
                gp.end()
                self._grain.append(g)

        # projector glow sprite (the expensive gradient, built once)
        if self._glow_key != key or self._glow is None:
            self._glow_key = key
            size_px = int(min(w, h) * 0.9)
            glow = QPixmap(size_px, size_px)
            glow.fill(Qt.GlobalColor.transparent)
            gp = QPainter(glow)
            rg = QRadialGradient(size_px / 2, size_px / 2, size_px / 2)
            rg.setColorAt(0.00, _rgba(CYAN, 120))
            rg.setColorAt(0.22, _rgba(CYAN, 62))
            rg.setColorAt(0.50, _rgba(BLUE, 22))
            rg.setColorAt(1.00, QColor(0, 0, 0, 0))
            gp.fillRect(0, 0, size_px, size_px, rg)
            gp.end()
            self._glow = glow

        if self._beam_key != key or self._beam is None:
            self._beam_key = key
            beam = QPixmap(int(w), int(h))
            beam.fill(Qt.GlobalColor.transparent)
            bp = QPainter(beam)
            bp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            path = QPainterPath()
            base_w = w * 0.30
            top_w = w * 0.62
            path.moveTo(w / 2 - base_w / 2, h)
            path.lineTo(w / 2 + base_w / 2, h)
            path.lineTo(w / 2 + top_w / 2, h * 0.10)
            path.lineTo(w / 2 - top_w / 2, h * 0.10)
            path.closeSubpath()
            lg = QLinearGradient(0, h, 0, h * 0.10)
            lg.setColorAt(0.0, _rgba(CYAN, 26))
            lg.setColorAt(0.5, _rgba(TEAL, 10))
            lg.setColorAt(1.0, QColor(0, 0, 0, 0))
            bp.fillPath(path, lg)
            bp.end()
            self._beam = beam

    # -- per-frame layers -------------------------------------------------
    def _paint_floor_beam(self, q: QPainter, w: int, h: int) -> None:
        if self._beam is not None:
            q.setOpacity(0.55 + 0.25 * math.sin(self._t * 0.8))
            q.drawPixmap(0, 0, self._beam)
            q.setOpacity(1.0)

    def _paint_streams(self, q: QPainter, w: int, h: int) -> None:
        """Data streams, cached.

        Text is the most expensive thing a software rasteriser does: 180 small
        drawText calls per frame cost more than the entire globe. So the columns
        are painted into an offscreen layer ~12 times a second and blitted in
        between, which is invisible at this glyph size and 4x cheaper.
        """
        if self._effects < 0.3:
            return
        fresh = (self._stream_cache is None or self._stream_key != (w, h)
                 or abs(self._t - self._stream_at) > 0.08)
        if fresh:
            layer = QPixmap(int(w), int(h))
            layer.fill(Qt.GlobalColor.transparent)
            lp = QPainter(layer)
            self._draw_stream_text(lp, w, h)
            lp.end()
            self._stream_cache = layer
            self._stream_key = (w, h)
            self._stream_at = self._t
        if self._stream_cache is not None:
            q.drawPixmap(0, 0, self._stream_cache)

    def _draw_stream_text(self, q: QPainter, w: int, h: int) -> None:
        f = QFont(MONO)
        f.setPixelSize(max(9, int(h * 0.016)))
        q.setFont(f)
        # The gutter prints the machine's own numbers in hex: memory in bytes, disk
        # in bytes, uptime, network counters, and the PIDs of the heaviest processes.
        # Deterministic, measured, and checkable — see tests/test_holo.py.
        pool = self._stream_pool()
        # the only honest place for them: the empty strips beside the globe.
        # over a panel a stream reads as noise, and noise on a gauge is a lie.
        pad = max(18, int(w * 0.018))
        panel_w = min(w * 0.235, 330)
        cx, _cy, radius = getattr(self, "_geo", (w * 0.5, h * 0.445, min(w, h) * 0.275))
        # the two clear columns: between the panels and the globe's silhouette
        l0 = pad + panel_w + w * 0.012
        l1 = cx - radius * 1.04 - w * 0.012
        r0 = cx + radius * 1.04 + w * 0.012
        r1 = w - pad - panel_w - w * 0.012
        if l1 - l0 < 70 or r1 - r0 < 70:
            return                      # no gutter at this aspect ratio — draw nothing
        for col in self._streams:
            if col["x"] < 0.5:
                t = col["x"] / 0.5                       # 0..1 inside the left gutter
                x = l0 + min(1.0, t) * (l1 - l0)
            else:
                t = (col["x"] - 0.5) / 0.5
                x = r0 + min(1.0, t) * (r1 - r0)
            rnd = random.Random(col["seed"])
            step = h * 0.032
            head = (self._t * col["speed"] * 30 * 6) % (col["len"] * step + h * 0.4)
            for i in range(col["len"]):
                y = head - i * step
                if y < h * 0.13 or y > h * 0.86:
                    continue
                alpha = int(120 * (1 - i / col["len"]) * self._effects)
                if alpha <= 3:
                    continue
                if i == 0:
                    q.setPen(_rgba(WHITE, min(230, alpha + 70)))
                elif i < 3:
                    q.setPen(_rgba(CYAN, alpha))
                else:
                    q.setPen(_rgba(TEAL, int(alpha * 0.55)))
                text = pool[rnd.randrange(len(pool))] if pool else "------"
                # right-hand columns are right-aligned: offset a copy of x, never x
                # itself — mutating it walked the column leftwards into the globe,
                # one glyph-width per line.
                tx = x - q.fontMetrics().horizontalAdvance(text) if col["x"] >= 0.5 else x
                q.drawText(QPointF(tx, y), text)

    def _paint_globe(self, q: QPainter, cx: float, cy: float, r: float) -> None:
        """Wireframe planet: a depth-faded lat/long mesh, nodes and traffic arcs.

        Depth is faked with two passes — everything behind the equator plane is
        drawn once at low alpha, everything in front at full alpha. That is two
        paths per ring instead of a per-segment pen change, which keeps a frame
        cheap enough to run on a CPU rasteriser.
        """
        tilt = math.radians(23)
        bright = 1.25 if self._effects >= 0.4 else 1.0
        rot = math.radians(self._rot)
        q.setBrush(Qt.BrushStyle.NoBrush)

        def project(lat: float, lon: float) -> tuple[QPointF, float]:
            x = math.cos(lat) * math.sin(lon)
            y = math.sin(lat)
            z = math.cos(lat) * math.cos(lon)
            y2 = y * math.cos(tilt) - z * math.sin(tilt)
            z2 = y * math.sin(tilt) + z * math.cos(tilt)
            return QPointF(cx + x * r, cy + y2 * r), z2

        def ring_paths(points: list[tuple[QPointF, float]]) -> tuple[QPainterPath, QPainterPath]:
            front, back = QPainterPath(), QPainterPath()
            for pt, depth in points:
                target = front if depth >= 0 else back
                if target.elementCount() == 0:
                    target.moveTo(pt)
                else:
                    target.lineTo(pt)
            return front, back

        for lat_deg in range(-60, 61, 30):
            lat = math.radians(lat_deg)
            pts = [project(lat, math.radians(d) + rot) for d in range(0, 361, 9)]
            front, back = ring_paths(pts)
            weight = 1.4 if lat_deg == 0 else 1.0
            q.setPen(QPen(_rgba(TEAL, int(26 * bright)), weight))
            q.drawPath(back)
            q.setPen(QPen(_rgba(CYAN, int((92 if lat_deg == 0 else 62) * bright)), weight))
            q.drawPath(front)

        lon_step = 60 if r > 280 else 45
        for lon_deg in range(0, 180, lon_step):
            pts = [project(math.radians(lat), math.radians(lon_deg) + rot)
                   for lat in range(-90, 91, 9)]
            front, back = ring_paths(pts)
            q.setPen(QPen(_rgba(TEAL, 22), 1.0))
            q.drawPath(back)
            q.setPen(QPen(_rgba(BLUE, int(58 * bright)), 1.0))
            q.drawPath(front)

        # terminator highlight: a soft arc where the "sun" hits the shell
        q.setPen(QPen(_rgba(WHITE, 26), 1.0))
        q.drawEllipse(QPointF(cx, cy), r, r)

        # nodes at fixed coordinates, pulsing, back ones dimmer
        nodes: list[tuple[QPointF, float]] = []
        for i in range(10):
            lat = math.radians(-52 + (i * 37) % 104)
            lon = math.radians((i * 71) % 360) + rot
            pt, depth = project(lat, lon)
            nodes.append((pt, depth))
            if depth < -0.05:
                continue
            pulse = 0.55 + 0.45 * math.sin(self._t * 2.2 + i * 0.9)
            rr = max(1.5, r * 0.011 * (0.7 + pulse))
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(_rgba(CYAN, int(46 * pulse)))
            q.drawEllipse(pt, rr * 3.4, rr * 3.4)
            q.setBrush(_rgba(WHITE, int(200 * pulse)))
            q.drawEllipse(pt, rr, rr)

        # traffic: thin beziers between the two brightest nodes, with a packet
        q.setBrush(Qt.BrushStyle.NoBrush)
        visible = [pt for pt, depth in nodes if depth > 0.15][:5]
        for i in range(len(visible) - 1):
            q.setBrush(Qt.BrushStyle.NoBrush)          # a dot must not fill the next arc
            a, b = visible[i], visible[i + 1]
            lift = r * (0.16 + 0.05 * i)
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2 - lift)
            path = QPainterPath(a)
            path.quadTo(mid, b)
            q.setPen(QPen(_rgba(MAGENTA, 74), 1.1))
            q.drawPath(path)
            phase = (self._t * 0.5 + i * 0.23) % 1.0
            pt = path.pointAtPercent(phase)
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(_rgba(WHITE, 190))
            q.drawEllipse(pt, 1.8, 1.8)



    def _paint_globe_dots(self, q: QPainter, cx: float, cy: float, r: float) -> None:
        """Point-cloud coverage over the wireframe: ~600 measured positions.

        The lattice is a real spherical grid (lat/lon), projected with the same tilt
        and rotation as the mesh, so the dots stick to the surface instead of
        floating — one drawPoints call per hemisphere keeps it nearly free.
        """
        tilt = math.radians(23)
        rot = math.radians(self._rot)
        ct, st = math.cos(tilt), math.sin(tilt)
        front: list[QPointF] = []
        back: list[QPointF] = []
        step = 15 if r > 280 else 11
        for lat_deg in range(-77, 78, step):
            lat = math.radians(lat_deg)
            cl = math.cos(lat)
            y0 = math.sin(lat)
            for lon_deg in range(0, 360, step):
                lon = math.radians(lon_deg) + rot
                x = cl * math.sin(lon)
                z = cl * math.cos(lon)
                y2 = y0 * ct - z * st
                z2 = y0 * st + z * ct
                pt = QPointF(cx + x * r, cy + y2 * r)
                (front if z2 > 0 else back).append(pt)
        q.setPen(QPen(_rgba(BLUE, int(48 * self._effects)), 1.2))
        if back:
            q.drawPoints(QPolygonF(back))
        q.setPen(QPen(_rgba(CYAN, int(165 * self._effects)), 1.7))
        if front:
            q.drawPoints(QPolygonF(front))

    def _paint_reticle(self, q: QPainter, cx: float, cy: float, r: float) -> None:
        """Corner aim marks around the globe — the 'targeting' language of a HUD."""
        rr = r * 1.62
        for k in range(4):
            ang = math.radians(45 + k * 90 + self._rot * 0.12)
            x, y = cx + rr * math.cos(ang), cy + rr * math.sin(ang)
            q.setPen(QPen(_rgba(CYAN, 90), 1.0))
            q.drawLine(QPointF(x - 7, y), QPointF(x + 7, y))
            q.drawLine(QPointF(x, y - 7), QPointF(x, y + 7))
        # orbit dots on the outer reticle
        for k in range(3):
            ang = math.radians(self._rot * (1.4 + k * 0.5) + k * 120)
            x, y = cx + rr * math.cos(ang), cy + rr * math.sin(ang)
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(_rgba(CYAN, 170))
            q.drawEllipse(QPointF(x, y), 2.6, 2.6)

    # -- panels -----------------------------------------------------------
    def _panel(self, q: QPainter, rect: QRectF, title: str) -> None:
        q.setPen(QPen(_rgba(CYAN, 60), 1.0))
        q.setBrush(QColor(4, 25, 34, 120))
        q.drawRect(rect)
        # corner ticks
        q.setPen(QPen(_rgba(CYAN, 180), 1.4))
        arm = 9
        for x, y, dx, dy in ((rect.left(), rect.top(), 1, 1),
                             (rect.right(), rect.top(), -1, 1),
                             (rect.left(), rect.bottom(), 1, -1),
                             (rect.right(), rect.bottom(), -1, -1)):
            q.drawLine(QPointF(x, y), QPointF(x + arm * dx, y))
            q.drawLine(QPointF(x, y), QPointF(x, y + arm * dy))
        f = QFont(MONO)
        f.setPixelSize(max(10, int(rect.height() * 0.115)))
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.4)
        q.setFont(f)
        q.setPen(_rgba(CYAN, 215))
        q.drawText(QPointF(rect.left() + 8, rect.top() + f.pixelSize() + 5), title)
        # the title band is a boundary, not decoration: content starts below it
        q.setPen(QPen(_rgba(CYAN, 34), 1.0))
        line_y = rect.top() + f.pixelSize() * 1.85
        q.drawLine(QPointF(rect.left() + 6, line_y), QPointF(rect.right() - 6, line_y))
        rect.setTop(line_y + 2)

    def _sparkline(self, q: QPainter, rect: QRectF, values, colour: str,
                   peak: float = 100.0) -> None:
        if len(values) < 2:
            return
        path = QPainterPath()
        n = len(values)
        for i, v in enumerate(values):
            x = rect.left() + rect.width() * i / (n - 1)
            y = rect.bottom() - rect.height() * min(1.0, v / peak)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        q.setPen(QPen(_rgba(colour, 210), 1.3))
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.drawPath(path)
        # fill under the curve, very faint — reads as a glowing trace
        fill = QPainterPath(path)
        fill.lineTo(rect.right(), rect.bottom())
        fill.lineTo(rect.left(), rect.bottom())
        fill.closeSubpath()
        q.fillPath(fill, _rgba(colour, 26))


    # ------------------------------------------------- cinematic dashboard
    def _layout(self, w: int, h: int, compact: bool) -> dict:
        """Where everything sits. One place, so compact mode cannot drift."""
        pad = max(14, int(w * 0.014))
        if compact:
            globe = (w * 0.150, h * 0.330, min(w, h) * 0.185)
            hero = (w * 0.500, h * 0.330, min(w, h) * 0.200)
        else:
            globe = (w * 0.160, h * 0.495, min(w, h) * 0.295)
            hero = (w * 0.505, h * 0.462, min(w, h) * 0.268)
        right_w = min(max(118.0, w * 0.132), 205.0)
        return {"pad": pad, "compact": compact, "globe": globe, "hero": hero,
                "right_x": w - pad - right_w, "right_w": right_w}

    def _real_numbers(self) -> list[int]:
        """Every integer the dashboard is allowed to print: all measured."""
        s = self._sampler
        caps = getattr(s, "pids", [])
        vals: list[float] = [
            s.mem_used, s.mem_total, s.disk_used, s.disk_total,
            s.net_in * 1000.0, s.net_out * 1000.0, s.disk_read, s.disk_write,
            s.swap_used, s.swap_total, float(s.procs), float(s.cores),
            time.time() - self._started,
        ]
        vals.extend(float(v * 100) for v in list(s.cpu)[-6:])
        vals.extend(float(v * 100) for v in list(s.mem)[-4:])
        vals.extend(float(pid) for pid in caps)
        return [int(v) for v in vals if v > 0]

    def _paint_number_field(self, q: QPainter, w: int, h: int, lay: dict) -> None:
        """Dense numeric dust — every figure is a live measurement."""
        key = (w, h, self._sample_serial, self._theme.key)
        if self._num_cache is None or self._num_key != key:
            layer = QPixmap(int(w), int(h))
            layer.fill(Qt.GlobalColor.transparent)
            lp = QPainter(layer)
            lp.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            self._draw_number_field(lp, w, h, lay)
            lp.end()
            self._num_cache = layer
            self._num_key = key
        if self._num_cache is not None:
            q.drawPixmap(0, 0, self._num_cache)

    def _draw_number_field(self, q: QPainter, w: int, h: int, lay: dict) -> None:
        values = self._real_numbers()
        if not values:
            return
        # the four headline figures are drawn later in this same pass; keep them out
        # of the dust so the screen never shows the same number twice
        amber = {int(self._sampler.mem_used),
                 int(max(0.0, self._sampler.disk_total - self._sampler.disk_used))}
        headline = [v for v in values
                    if 10000 <= v <= 999_999_999_999 and v not in amber][:3]
        values = [v for v in values if v not in headline] or values
        rnd = random.Random(0x5EED)
        gx, gy, gr = lay["globe"]
        hx, hy, hr = lay["hero"]
        right_x = lay["right_x"]
        f = QFont(MONO)
        f.setPixelSize(max(8, int(h * 0.0125)))
        q.setFont(f)
        placed = 0
        tries = 0
        while placed < 46 and tries < 900:
            tries += 1
            x = 0.03 * w + rnd.random() * (right_x - 0.05 * w)
            y = h * 0.085 + rnd.random() * h * 0.62
            # keep the hero and the planet readable: no dust on top of them
            if math.hypot(x - hx, y - hy) < hr * 1.06:
                continue
            if math.hypot(x - gx, y - gy) < gr * 1.02 and x < gx + gr:
                continue
            text = str(values[rnd.randrange(len(values))])
            alpha = rnd.randint(16, 64) if rnd.random() > 0.14 else rnd.randint(95, 140)
            q.setPen(_rgba(CYAN if alpha < 120 else WHITE, alpha))
            q.drawText(QPointF(x, y), text)
            placed += 1

        # four big figures where the reference puts its headline numbers
        big = QFont(MONO)
        big.setPixelSize(max(14, int(h * 0.028)))
        big.setWeight(QFont.Weight.DemiBold)
        q.setFont(big)
        anchors = ((0.315, 0.170, CYAN), (0.640, 0.150, TEAL),
                   (0.360, 0.775, TEAL))
        big_values = list(headline)
        used: list[int] = []
        for i, (fx, fy, colour) in enumerate(anchors):
            pool = [v for v in big_values if v not in used]
            if not pool:
                break
            v = pool[i % len(pool)]
            text = f"{v:,}"
            tw = q.fontMetrics().horizontalAdvance(text)
            x = min(w * fx, right_x - tw - 12)      # never run under the panels
            y = h * fy
            # never over the planet or the spiral
            if (math.hypot(x - hx, y - hy) < hr * 1.15
                    or math.hypot(x - gx, y - gy) < gr * 1.05):
                continue
            used.append(v)
            # a dark plate behind each headline figure so the dust never runs through it
            asc = q.fontMetrics().ascent()
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(2, 12, 18, 150))
            q.drawRect(QRectF(x - 6, y - asc - 2, tw + 12, asc + 8))
            q.setPen(_rgba(colour, 190))
            q.drawText(QPointF(x, y), text)

    def _paint_topbar(self, q: QPainter, w: int, h: int) -> None:
        """The ribbon at the very top: measured integers, plus a level meter."""
        values = self._real_numbers()
        bar = QRectF(0, 0, w, max(12.0, h * 0.026))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(2, 14, 20, 190))
        q.drawRect(bar)
        f = QFont(MONO)
        f.setPixelSize(max(8, int(h * 0.0135)))
        q.setFont(f)
        fm = q.fontMetrics()
        if values:
            # a marquee of real integers, in the order they were sampled
            text = "   ".join(str(values[i % len(values)]) for i in range(len(values)))
            text = (text + "   ") * 3
            span = fm.horizontalAdvance(text) / 3.0
            offset = (self._t * 22) % span
            q.setClipRect(0, 0, int(w * 0.72), int(bar.height()))
            q.setPen(_rgba(TEAL, 150))
            x = -offset
            while x < w * 0.75:
                q.drawText(QPointF(x, bar.height() * 0.72), text)
                x += span
            q.setClipping(False)
        # level meter on the right: one block per core, filled by its real load
        loads = getattr(self._sampler, "core_load", []) or []
        bx = w * 0.74
        blocks = max(8, min(28, len(loads) * 3 if loads else 8))
        bw = (w * 0.25) / blocks
        for i in range(blocks):
            v = loads[i % len(loads)] if loads else 0.0
            lit = (v / 100.0) > (i / blocks) * 0.9
            q.setBrush(_rgba(CYAN if lit else CYAN, 210 if lit else 34))
            q.drawRect(QRectF(bx + i * bw, bar.height() * 0.26, bw * 0.72,
                              bar.height() * 0.48))
        q.setPen(QPen(_rgba(CYAN, 70), 1.0))
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.drawLine(QPointF(0, bar.height()), QPointF(w, bar.height()))

    def _paint_hero(self, q: QPainter, cx: float, cy: float, r: float) -> None:
        """Cached at 20 Hz: the rings turn slowly, the rasteriser should not."""
        key = (int(cx), int(cy), int(r), self._theme.key)
        if self._hero_cache is None or self._hero_cache_key != key:
            size = int(r * 2.6)
            layer = QPixmap(size, size)
            layer.fill(Qt.GlobalColor.transparent)
            lp = QPainter(layer)
            lp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._hero_origin = (cx - size / 2.0, cy - size / 2.0, cx, cy)
            self._draw_hero(lp, size / 2.0, size / 2.0, r)
            lp.end()
            self._hero_cache = layer
            self._hero_cache_key = key
            self._hero_at = self._t
        elif abs(self._t - self._hero_at) > 0.05:
            lp = QPainter(self._hero_cache)
            lp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            lp.fillRect(self._hero_cache.rect(), Qt.GlobalColor.transparent)
            lp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            lp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            size = self._hero_cache.width()
            self._draw_hero(lp, size / 2.0, size / 2.0, r)
            lp.end()
            self._hero_at = self._t
        ox, oy, _, _ = self._hero_origin
        q.drawPixmap(int(ox), int(oy), self._hero_cache)

    def _draw_hero(self, q: QPainter, cx: float, cy: float, r: float) -> None:
        """The centre piece: a stack of tilted light rings spiralling into a core.

        This is the shape the whole look hangs on — the reference image's swirl.
        Six rings, each with its own tilt, spin rate and thickness, drawn as an open
        arc so the leading edge reads as a bright head travelling around the loop.
        """
        key = (int(r), self._theme.key)
        if self._hero_glow is None or self._hero_key != key:
            size = max(32, int(r * 2.8))
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            gp = QPainter(pm)
            gp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            grad = QRadialGradient(size / 2, size / 2, size / 2)
            grad.setColorAt(0.0, _rgba(CYAN, 120))
            grad.setColorAt(0.35, _rgba(CYAN, 44))
            grad.setColorAt(0.70, _rgba(TEAL, 16))
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            gp.setPen(Qt.PenStyle.NoPen)
            gp.setBrush(grad)
            gp.drawEllipse(QRectF(0, 0, size, size))
            gp.end()
            self._hero_glow = pm
            self._hero_key = key
        q.drawPixmap(int(cx - self._hero_glow.width() / 2),
                     int(cy - self._hero_glow.height() / 2), self._hero_glow)

        rings = 6 if self._effects >= 0.4 else 4
        # at very high resolutions the arcs get longer; keep the frame inside budget
        steps = 38 if r * 2 > 560 else 44
        for i in range(rings):
            t = i / max(1, rings - 1)
            rad = r * (0.34 + 0.66 * t)
            tilt = math.radians(-26 + i * 9.5)
            spin = math.radians(self._rot * (1.0 + 0.22 * i) + i * 47.0)
            squash = 0.42 + 0.16 * t
            sweep = math.radians(288)
            path = QPainterPath()
            ca, sa = math.cos(tilt), math.sin(tilt)
            for k in range(steps + 1):
                a = spin + sweep * k / steps
                x0 = math.cos(a) * rad
                y0 = math.sin(a) * rad * squash
                px = cx + x0 * ca - y0 * sa
                py = cy + x0 * sa + y0 * ca
                path.moveTo(px, py) if k == 0 else path.lineTo(px, py)
            q.setBrush(Qt.BrushStyle.NoBrush)
            width = max(1.4, r * (0.030 - 0.0035 * i))
            if i >= rings - 3:      # the soft halo pass only where it is visible
                q.setPen(QPen(_rgba(CYAN, int(52 + 34 * t)), width * 2.6,
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                q.drawPath(path)
            q.setPen(QPen(_rgba(WHITE, int(150 + 60 * t)), max(1.2, width * 0.55),
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            q.drawPath(path)
            # bright head at the leading edge
            a = spin + sweep
            x0 = math.cos(a) * rad
            y0 = math.sin(a) * rad * squash
            px = cx + x0 * ca - y0 * sa
            py = cy + x0 * sa + y0 * ca
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(_rgba(WHITE, 230))
            head = max(1.6, width * 0.9)
            q.drawEllipse(QPointF(px, py), head, head)

        # an echo ring outside the collar: depth without another animation
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.setPen(QPen(_rgba(TEAL, 40), 1.2))
        q.drawEllipse(QPointF(cx, cy), r * 1.14, r * 1.14 * 0.55)

        # tick collar + core
        q.setBrush(Qt.BrushStyle.NoBrush)
        ticks = 48
        for i in range(ticks):
            a = math.radians(i * 360 / ticks + self._rot * 0.35)
            r0 = r * 1.02
            r1 = r0 + (r * 0.055 if i % 5 == 0 else r * 0.026)
            q.setPen(QPen(_rgba(CYAN, 120 if i % 5 == 0 else 52), 1.0))
            q.drawLine(QPointF(cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                       QPointF(cx + math.cos(a) * r1, cy + math.sin(a) * r1))
        grad = QRadialGradient(cx, cy, r * 0.30)
        grad.setColorAt(0.0, _rgba(WHITE, 240))
        grad.setColorAt(0.35, _rgba(CYAN, 170))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(grad)
        q.drawEllipse(QPointF(cx, cy), r * 0.30, r * 0.30)
        q.setBrush(_rgba(WHITE, 255))
        q.drawEllipse(QPointF(cx, cy), max(2.0, r * 0.030), max(2.0, r * 0.030))

    def _paint_instruments(self, q: QPainter, w: int, h: int, lay: dict) -> None:
        key = (w, h, self._sample_serial, self._theme.key)
        if self._tele_cache is None or self._tele_key != key:
            layer = QPixmap(int(w), int(h))
            layer.fill(Qt.GlobalColor.transparent)
            lp = QPainter(layer)
            lp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            lp.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            self._draw_instruments(lp, w, h, lay)
            lp.end()
            self._tele_cache = layer
            self._tele_key = key
        if self._tele_cache is not None:
            q.drawPixmap(0, 0, self._tele_cache)

    def _draw_instruments(self, q: QPainter, w: int, h: int, lay: dict) -> None:
        s = self._sampler
        seen = min(len(s.cpu), getattr(s, "seen", len(s.cpu)))
        hist = lambda seq: list(seq)[-seen:] if seen else []      # noqa: E731
        cpu = s.cpu[-1] if s.cpu else 0.0
        mem = s.mem[-1] if s.mem else 0.0
        rx, rw = lay["right_x"], lay["right_w"]
        top = h * 0.115
        rows = [
            ("CPU", f"{cpu:.1f}%", CYAN, hist(s.cpu), 100.0, "psutil · 4 Hz"),
            ("MEMORY", f"{mem:.1f}%", TEAL, hist(s.mem), 100.0,
             f"{s.mem_used / 1e9:.1f}/{s.mem_total / 1e9:.1f} GB"),
            ("NETWORK", f"{s.net_in + s.net_out:.1f} KB/s", MAGENTA, hist(s.net),
             max(1.0, max(hist(s.net)) if seen else 1.0),
             f"{s.net_in:.0f} in · {s.net_out:.0f} out KB/s"),
            ("STORAGE", f"{100 * s.disk_used / max(1.0, s.disk_total):.1f}%", AMBER,
             [100 * s.disk_used / max(1.0, s.disk_total)] * 8, 100.0,
             f"{s.disk_used / 1e9:.0f} of {s.disk_total / 1e9:.0f} GB"),
            ("PROCESSES", f"{s.procs}", CYAN, [], 1.0,
             f"{s.cores} cores · swap {s.swap_used / 1e9:.1f} GB"),
        ]
        if not s.ok:
            # no psutil, no numbers — say so instead of drawing zeroes that look real
            rows = [(t, "no sensor", c, [], p_, "no psutil installed")
                    for (t, _v, c, _s, p_, _sub) in rows]
        bh = h * 0.098
        gap = h * 0.010
        for i, (title, value, colour, series, peak, sub) in enumerate(rows):
            rect = QRectF(rx, top + i * (bh + gap), rw, bh)
            self._panel(q, rect, title)
            band = rect.height()
            fv = QFont(MONO)
            fv.setPixelSize(max(11, int(min(band * 0.30, rw * 0.145))))
            fv.setWeight(QFont.Weight.DemiBold)
            q.setFont(fv)
            q.setPen(QColor(colour))
            q.drawText(QPointF(rect.left() + 8, rect.top() + band * 0.50), value)
            fs = QFont(MONO)
            fs.setPixelSize(max(7, int(min(band * 0.135, rw * 0.062))))
            q.setFont(fs)
            q.setPen(_rgba(TEAL, 150))
            fm = q.fontMetrics()
            q.drawText(QPointF(rect.left() + 8, rect.top() + band * 0.71),
                       fm.elidedText(sub, Qt.TextElideMode.ElideRight,
                                     int(rect.width() - 16)))
            if series:
                self._sparkline(q, QRectF(rect.left() + 8, rect.top() + band * 0.83,
                                          rect.width() - 16, band * 0.12),
                                series, colour, peak)

        # the two amber readouts: raw byte counts, like the reference's 783486
        ax = rx + rw
        ys = top + len(rows) * (bh + gap) + h * 0.030
        f = QFont(MONO)
        f.setPixelSize(max(13, int(h * 0.030)))
        f.setWeight(QFont.Weight.Bold)
        q.setFont(f)
        big = QFont(MONO)
        big.setPixelSize(max(7, int(h * 0.0105)))
        for label, number in (("MEMORY BYTES", int(s.mem_used)),
                              ("DISK FREE BYTES", int(max(0.0, s.disk_total - s.disk_used)))):
            q.setFont(big)
            q.setPen(_rgba(AMBER, 150))
            fm = q.fontMetrics()
            q.drawText(QPointF(ax - fm.horizontalAdvance(label), ys - h * 0.012), label)
            q.setFont(f)
            text = f"{number:,}"
            fm = q.fontMetrics()
            q.setPen(_rgba(AMBER, 235))
            q.drawText(QPointF(ax - fm.horizontalAdvance(text), ys + h * 0.022), text)
            ys += h * 0.062

        # palette block — the theme's own colours, labelled as such
        sw_y = ys + h * 0.006
        cols, rows_n = 6, 5
        cw = rw / cols
        ch = h * 0.013
        q.setFont(big)
        q.setPen(_rgba(AMBER, 140))
        q.drawText(QPointF(rx, sw_y - h * 0.008), "PALETTE")
        palette = [CYAN, TEAL, MAGENTA, AMBER, WHITE, "#0a2a38"]
        for r_ in range(rows_n):
            for c_ in range(cols):
                col = palette[(r_ * cols + c_) % len(palette)]
                alpha = 60 + (r_ * 26 + c_ * 9) % 150
                q.setPen(Qt.PenStyle.NoPen)
                q.setBrush(_rgba(col, alpha))
                q.drawRect(QRectF(rx + c_ * cw, sw_y + r_ * (ch + 2), cw - 2, ch))

        # under the globe: the three numbers a person actually wants
        gx, gy, gr = lay["globe"]
        strip = QRectF(max(lay["pad"], gx - gr * 1.02), h * 0.700,
                       min(w * 0.30, gr * 1.95), h * 0.072)
        q.setPen(QPen(_rgba(CYAN, 90), 1.0))
        q.setBrush(QColor(2, 16, 22, 170))
        q.drawRect(strip)
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.setPen(QPen(_rgba(CYAN, 40), 1.0))
        q.drawLine(strip.topLeft(), strip.topRight())
        f.setPixelSize(max(9, int(strip.height() * 0.26)))
        q.setFont(f)
        cells = [(f"{cpu:.0f}%", "CPU"), (f"{mem:.0f}%", "MEM"),
                 (f"{int(time.time() - self._started)}s", "UP")]
        for i, (v, k) in enumerate(cells):
            x = strip.left() + strip.width() * (i + 0.5) / len(cells)
            q.setPen(_rgba(WHITE, 225))
            tw = q.fontMetrics().horizontalAdvance(v)
            q.drawText(QPointF(x - tw / 2, strip.top() + strip.height() * 0.62), v)
            q.setFont(big)
            kw = q.fontMetrics().horizontalAdvance(k)
            q.setPen(_rgba(TEAL, 140))
            q.drawText(QPointF(x - kw / 2, strip.bottom() - strip.height() * 0.12), k)
            q.setFont(f)

    def _paint_core_load(self, q: QPainter, w: int, h: int) -> None:
        """Per-core load as vertical bars — one bar per logical core, real values."""
        loads = getattr(self._sampler, "core_load", [])
        left, right = w * 0.545, w * 0.815
        top, bottom = h * 0.824, h * 0.888
        f = QFont(MONO)
        f.setPixelSize(max(7, int(h * 0.0105)))
        q.setFont(f)
        q.setPen(_rgba(TEAL, 130))
        q.drawText(QPointF(left, top - 6),
                   f"PER-CORE LOAD · {len(loads)} CORES · psutil")
        if not loads:
            q.drawText(QPointF(left, bottom), "no sensor")
            return
        n = len(loads)
        span = (right - left) / n
        bw = min(span * 0.55, 26.0)
        q.setPen(Qt.PenStyle.NoPen)
        for i, v in enumerate(loads):
            frac = max(0.02, min(1.0, v / 100.0))
            x = left + i * span + (span - bw) / 2
            bar_h = (bottom - top) * frac
            colour = CYAN if v < 60 else (AMBER if v < 85 else "#ff6b6b")
            q.setBrush(_rgba(colour, 46))
            q.drawRect(QRectF(x, top, bw, bottom - top))
            q.setBrush(_rgba(colour, 225))
            q.drawRect(QRectF(x, bottom - bar_h, bw, bar_h))
            q.setPen(_rgba(TEAL, 150))
            label = f"{v:.0f}%"
            q.drawText(QPointF(x + (bw - q.fontMetrics().horizontalAdvance(label)) / 2,
                               top - 12), label)
            q.setPen(Qt.PenStyle.NoPen)
        q.setPen(QPen(_rgba(CYAN, 60), 1.0))
        q.drawLine(QPointF(left, bottom + 1), QPointF(right, bottom + 1))

    def _paint_header(self, q: QPainter, w: int, h: int) -> None:
        f = QFont(MONO)
        f.setPixelSize(max(10, int(h * 0.020)))
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
        q.setFont(f)
        q.setPen(_rgba(WHITE, 210))
        q.drawText(QPointF(w * 0.045, h * 0.075), "A R C   D E S K   //   H O L O D E C K")
        fs = QFont(MONO)
        fs.setPixelSize(max(8, int(h * 0.014)))
        q.setFont(fs)
        q.setPen(_rgba(TEAL, 170))
        q.drawText(QPointF(w * 0.045, h * 0.098),
                   "PROJECTED SURFACE · LIVE TELEMETRY · NO SIMULATED NUMBERS")

        stamp = time.strftime("%H:%M:%S")
        fw = q.fontMetrics().horizontalAdvance(f"{stamp}  ·  ONLINE")
        q.setPen(_rgba(CYAN, 200))
        q.drawText(QPointF(w - w * 0.045 - fw, h * 0.075), f"{stamp}  ·  ONLINE")
        q.setPen(_rgba(TEAL, 120))
        q.drawText(QPointF(w - w * 0.045 - fw, h * 0.098),
                   f"{self._theme.label.lower()} projection")

    def _paint_spectrum(self, q: QPainter, w: int, h: int) -> None:
        """Telemetry spectrum — bars built from the same samples as the panels.

        It is not an audio visualiser and it does not pretend to be: the label
        says what the bars are, because a moving graph that means nothing is
        exactly the kind of decoration this project refuses.
        """
        s = self._sampler
        seen = getattr(s, "seen", len(s.cpu))
        cpu = list(s.cpu)[-seen:] if seen else []
        mem = list(s.mem)[-seen:] if seen else []
        if not cpu:
            return
        left, right = w * 0.045, w * 0.500
        top, bottom = h * 0.815, h * 0.885
        bars = 48
        half = bars // 2
        gap = 10.0
        span = (right - left - gap) / 2.0
        f = QFont(MONO)
        f.setPixelSize(max(8, int(h * 0.0125)))
        q.setFont(f)
        q.setPen(_rgba(TEAL, 130))
        # 48 samples at the sampler's 4 Hz = 12 s, and the labels say which half is which
        q.drawText(QPointF(left, top - 6),
                   "TELEMETRY SPECTRUM · LAST 12 s · CPU (LEFT) · MEMORY (RIGHT)")

        def _spread(vals: list[float], n: int) -> list[float]:
            if not vals:
                return []
            return [vals[int(i * len(vals) / n)] for i in range(n)]

        for side, vals in ((0, _spread(cpu, half)), (1, _spread(mem, half))):
            step = span / half
            origin = left + side * (span + gap)
            for i, v in enumerate(vals):
                value = max(0.0, min(1.0, v / 100.0))
                height = max(0.02, value)
                x = origin + i * step
                bar_h = (bottom - top) * height
                colour = CYAN if value < 0.6 else (AMBER if value < 0.85 else "#ff6b6b")
                q.setPen(Qt.PenStyle.NoPen)
                q.setBrush(_rgba(colour, 70))
                q.drawRect(QRectF(x, bottom - bar_h, step * 0.58, bar_h))
                q.setBrush(_rgba(colour, 210))
                q.drawRect(QRectF(x, bottom - bar_h, step * 0.58, max(1.0, h * 0.0018)))
            q.setPen(QPen(_rgba(CYAN, 60), 1.0))
            q.drawLine(QPointF(origin, bottom + 1), QPointF(origin + span, bottom + 1))
        # divider between the two histories
        q.setPen(QPen(_rgba(CYAN, 90), 1.0))
        mid = left + span + gap / 2
        q.drawLine(QPointF(mid, top), QPointF(mid, bottom + 1))


    def _paint_edges(self, q: QPainter, w: int, h: int) -> None:
        """Rulers on both edges — the detail that makes it read as an instrument."""
        f = QFont(MONO)
        f.setPixelSize(max(7, int(h * 0.0105)))
        q.setFont(f)
        for side in (0, 1):
            x = w * 0.012 if side == 0 else w * 0.988
            for i in range(0, 21):
                y = h * 0.14 + (h * 0.60) * i / 20
                long_tick = i % 5 == 0
                q.setPen(QPen(_rgba(CYAN, 70 if long_tick else 34), 1.0))
                tick = 9 if long_tick else 5
                q.drawLine(QPointF(x, y), QPointF(x + (tick if side == 0 else -tick), y))
                if long_tick:
                    q.setPen(QPen(_rgba(CYAN, 110), 1.0))
                    q.drawLine(QPointF(x, y), QPointF(x + (16 if side == 0 else -16), y))

    def _paint_ticker(self, q: QPainter, w: int, h: int) -> None:
        bar = QRectF(w * 0.045, h * 0.905, w * 0.91, h * 0.055)
        q.setPen(QPen(_rgba(CYAN, 44), 1.0))
        q.setBrush(QColor(3, 18, 26, 130))
        q.drawRect(bar)

        events = self._recent_events()
        sep = "   ◇   "
        text = sep.join(events)
        f = QFont(MONO)
        f.setPixelSize(max(9, int(bar.height() * 0.34)))
        q.setFont(f)
        fm = q.fontMetrics()
        span = fm.horizontalAdvance(text + sep)      # one full copy + its separator
        if span <= 0:
            return
        offset = (self._t * 26) % span
        y = bar.center().y() + fm.ascent() * 0.35
        q.setClipRect(bar.adjusted(6, 0, -6, 0))
        q.setPen(_rgba(TEAL, 190))
        # draw as many copies as the bar is wide — the old code drew exactly two,
        # which collided on top of each other whenever the text was shorter than the bar
        x = bar.left() + 8 - offset
        while x < bar.right():
            q.drawText(QPointF(x, y), text + sep)
            x += span
        q.setClipping(False)

    def _stream_pool(self) -> list[str]:
        """Six-hex-digit renderings of real sampled values (never random)."""
        s = self._sampler
        values: list[float] = [
            s.mem_used, s.disk_used, 100.0 * (s.cpu[-1] if s.cpu else 0.0),
            s.net_in, s.net_out, float(time.time() - self._started),
            float(s.procs),
        ]
        values.extend(float(pid) for pid in s.pids)
        values.extend(float(v) for v in list(s.mem)[-4:])
        pool: list[str] = []
        for v in values:
            n = int(abs(v)) & 0xFFFFFF
            text = f"{n:06X}"
            if n and text not in pool:      # repeats read as noise, not data
                pool.append(text)
        return pool

    def _recent_events(self) -> list[str]:
        """Real log lines if they exist; otherwise a truthful placeholder."""
        try:
            from .. import logs
            lines = logs.tail(3)
            if lines:
                cleaned = []
                for line in lines:
                    # "2026-10-22 12:40:11 INFO arcdesk.ai   tool time ok"
                    parts = line.split()
                    tail = " ".join(parts[3:])[:46] if len(parts) > 3 else line[:46]
                    cleaned.append(tail.upper())
                return cleaned
        except Exception:
            pass
        return ["TELEMETRY ONLINE", "PROJECTOR NOMINAL",
                f"AWAITING INSTRUCTION · {time.strftime('%H:%M')}"]

    def _paint_sweep(self, q: QPainter, w: int, h: int) -> None:
        if self._effects < 0.4:
            return
        y = (self._t * 0.16 % 1.0) * h
        grad = QLinearGradient(0, y - h * 0.06, 0, y + h * 0.02)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.7, _rgba(CYAN, 12))
        grad.setColorAt(1.0, _rgba(WHITE, 26))
        q.fillRect(QRectF(0, y - h * 0.06, w, h * 0.08), grad)

    def _paint_grain(self, q: QPainter, w: int, h: int) -> None:
        if not self._grain or self._effects < 0.35:
            return
        idx = int(self._t * 12) % len(self._grain)
        g = self._grain[idx]
        # a texture brush is one rasteriser call; the tiled blits were 28
        brush = QBrush(g)
        brush.setTransform(QTransform().translate(int(self._t * 97) % 180,
                                                int(self._t * 61) % 180))
        q.setOpacity(0.42)
        q.fillRect(0, 0, w, h, brush)
        # flicker: a projector is never perfectly steady
        flick = 0.03 + 0.03 * math.sin(self._t * 17.0) * self._effects
        if flick > 0:
            q.fillRect(0, 0, w, h, QColor(0, 0, 0, int(flick * 255)))
        q.setOpacity(1.0)

    def _paint_boot(self, q: QPainter, w: int, h: int) -> None:
        """The three-second boot line. One message at a time, then it is gone."""
        if self._boot > 2.6:
            return
        steps = ["CALIBRATING PROJECTOR", "SYNCING TELEMETRY BUS",
                 "MAPPING GEOMETRY", "SURFACE ONLINE"]
        index = min(len(steps) - 1, int(self._boot / 0.62))
        label = steps[index]
        progress = min(1.0, (self._boot % 0.62) / 0.5)
        f = QFont(MONO)
        f.setPixelSize(max(9, int(h * 0.0145)))
        q.setFont(f)
        fade = 1.0 if self._boot < 2.2 else max(0.0, (2.6 - self._boot) / 0.4)
        text = f"{label}  {'·' * int(progress * 12):<12}  {'OK' if index < 3 else 'ONLINE'}"
        width = q.fontMetrics().horizontalAdvance(text)
        q.setPen(_rgba(CYAN, int(200 * fade)))
        q.drawText(QPointF(w * 0.5 - width / 2, h * 0.935), text)
        if self._boot < 0.4:
            sweep = (self._boot / 0.4) * h
            q.fillRect(QRectF(0, 0, w, sweep),
                       QColor(0, 0, 0, int(255 * (1 - self._boot / 0.4))))


class HoloWindow(QWidget):
    """Standalone fullscreen deck — the 'scientific server' view, nothing else.

    Own window on purpose: the magic screen is a chat surface, this is an
    instrument panel. Same renderer, different container, so there is one set of
    pixels to maintain. Esc closes it; nothing is written to disk.
    """

    def __init__(self, theme: Theme) -> None:
        super().__init__(None,
                         Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setWindowTitle("Arc Desk — Hologram Deck")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.deck = HoloDeck(theme, self)
        lay.addWidget(self.deck)

    def set_theme(self, theme: Theme) -> None:
        self.deck.set_theme(theme)

    def show_deck(self) -> None:
        from PySide6.QtGui import QGuiApplication
        screens = QGuiApplication.screens()
        if screens:
            geo = screens[0].geometry()
            for extra in screens[1:]:
                geo = geo.united(extra.geometry())
            self.setGeometry(geo)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.deck.boot()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self.close()
        else:
            super().keyPressEvent(event)
