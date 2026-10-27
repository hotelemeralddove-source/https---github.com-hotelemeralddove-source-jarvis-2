"""The Magic screen — one picture of what JARVIS is, drawn as a web.

The report that reshaped it: *"important ah magic begin section la ena nadakuthu
nay enakku puriyala... romba complicate web mathiri iruku... enakku clear spider web
mathiri irukanum"*. It was a hologram globe, a clock, six unlabelled tiles, a work
panel and a command line all at once: pretty, and nobody could say what any of it
was for.

So it is now literally a spider web, and every strand says what it is:

        FILES  ──╮        ╭── NOTEPAD
                 ╰── JARVIS ──╯
        SETTINGS ─╯        ╰── CALC      (six strands, six plain sentences)

* the centre is JARVIS, with the one line that matters — what it is doing RIGHT NOW;
* each strand leads to one thing, named the way a person would name it, with a short
  plain-English line under it saying what the click does;
* a strand lights up when that part is actually in use (from the activity record);
* a finished step is written at the bottom left as it happens, with its timing.

Still **just a window**: your Windows session underneath is untouched, and the moment
this hides you are back — no shell restart, no reboot, no lost Start menu. That is
said on the screen too, because "what IS this?" was a fair question.
"""
from __future__ import annotations

import math
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QLinearGradient, QPainter,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from .. import activity as _activity
from ..theme import Theme
from .holo import HoloDeck
from ..ticker import ticker

#: How often the "what is happening" panel re-reads the activity record. Four times a
#: second is faster than a person reads and slower than a repaint could cost.
WORK_POLL_MS = 250

#: (label, target). The first four are OWNED by this app: they open in the dock inside
#: the deck. The last two are Windows programs/browser, which cannot live in here - those
#: are launched and brought to the FRONT so a click never looks like it did nothing.
APPS = [
    ("FILES", "dock:files"), ("NOTEPAD", "dock:notepad"), ("CALC", "dock:calc"),
    ("TASK MGR", "dock:processes"), ("SETTINGS", "settings"),
    ("BROWSER", "https://www.google.com"),
]

#: What each strand is, in words a person would use. This is the whole point of the
#: screen: no label is allowed to be unexplained.
STRANDS = {
    "FILES": "your folders, opened in here",
    "NOTEPAD": "write something, stays in here",
    "CALC": "quick maths, no spreadsheet",
    "TASK MGR": "what is running right now",
    "SETTINGS": "voice, wake word, the rest",
    "BROWSER": "the web, as a normal window",
}

#: Strands are laid out on an ellipse, clockwise from the top. 60 degrees apart.
STRAND_ANGLES = [(-90 + i * 60) for i in range(len(APPS))]


class MagicScreen(QWidget):
    exit_requested = Signal()
    command = Signal(str)
    app_requested = Signal(str)

    def __init__(self, theme: Theme, exit_phrase: str = "bye jarvis") -> None:
        super().__init__()
        self._theme = theme
        self._exit_phrase = exit_phrase
        self._t = 0.0
        # Plain words, not jargon: the screen says what it is for, then what it is doing.
        self._status = "JARVIS · READY"
        self._work: list[str] = []          # finished steps, newest last
        self._now = ""                      # the step in progress, one line
        self._strokes = -1                  # activity counter we last drew
        self._work_age = 0.0

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(6)

        # The six apps are NOT widgets any more. They are the strands of the web, painted
        # (see _strand_rects) and hit-tested, so the picture and the click target are the
        # same thing - one object to look at, one object to click. Widgets on top of a
        # painted background is how the old screen ended up looking like a puzzle.
        self._hover = -1
        self.setMouseTracking(True)

        lay.addSpacing(26)
        self.input = QLineEdit()
        self.input.setObjectName("magicInput")
        self.input.setPlaceholderText('Speak, or type — "open google"  ·  "system report"')
        self.input.setMinimumHeight(38)
        self.input.setMinimumWidth(540)
        self.input.setMaximumWidth(560)
        self.input.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.input.returnPressed.connect(self._submit)
        lay.addWidget(self.input, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(2)

        # Apps that open INSIDE the deck. Before this, every tile started a Windows
        # process which landed *under* the fullscreen magic screen: "click pana athu
        # background la windows la than open aaguthu".
        self._opening = ""
        from .appdock import AppDock
        self.dock = AppDock(theme, self)
        self.dock.setFixedWidth(min(560, max(360, int(self.width() or 900) * 0.42)))
        self.dock.hide()

        # one renderer, painted into this widget's painter (no child widget, so
        # the buttons and the input stay above it without z-order tricks)
        self._holo = HoloDeck(theme)
        self._holo.autonomous = False

        self.setStyleSheet(self._qss(theme))
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self.update)
        self._clock.start()
        ticker().tick.connect(self._on_tick)

        # The report was "holo ok, aana ena work nadakutho theriyala". So the screen now
        # shows the work itself: the request, the step in progress, and the steps that
        # finished with how long each took. It reads the same record the dashboard uses,
        # polled 4x a second, and repaints only when that record actually changed.
        self._work_timer = QTimer(self)
        self._work_timer.setInterval(WORK_POLL_MS)
        self._work_timer.timeout.connect(self._poll_work)
        self._work_timer.start()

    # -- the web ---------------------------------------------------------
    def _web_geometry(self) -> tuple[float, float, float, float]:
        """(cx, cy, rx, ry) — the ellipse the six strands sit on."""
        w, h = max(640, self.width()), max(480, self.height())
        cx = w * 0.5
        # cy/ry chosen so the top strand clears the two header lines and the bottom one
        # clears the command box. Measured at 1366x768 and 1920x1080.
        cy = h * 0.415
        # scales with the screen: a 1080p web was a small knot in the middle before
        rx = min(w * 0.32, 600.0)
        ry = min(h * 0.26, 268.0)
        # and the bottom strand must never reach the command box (measured, not guessed)
        node_h = max(56.0, min(74.0, h * 0.075))
        ry = min(ry, max(60.0, h * 0.695 - node_h / 2 - cy))
        return cx, cy, rx, ry

    def _strand_rects(self) -> list[tuple[QRectF, str, str, str]]:
        """[(rect, label, explanation, target)] for the six strands, in APPS order."""
        import math as _m
        cx, cy, rx, ry = self._web_geometry()
        node_w = min(268.0, max(150.0, self.width() * 0.165))
        node_h = max(56.0, min(74.0, self.height() * 0.075))
        out: list[tuple[QRectF, str, str, str]] = []
        for (label, target), angle in zip(APPS, STRAND_ANGLES):
            rad = _m.radians(angle)
            x = cx + rx * _m.cos(rad)
            y = cy + ry * _m.sin(rad)
            rect = QRectF(x - node_w / 2, y - node_h / 2, node_w, node_h)
            out.append((rect, label, STRANDS.get(label, ""), target))
        return out

    @staticmethod
    def _fit(q: QPainter, text: str, max_w: float) -> str:
        """Shorten `text` until it fits, ending in an ellipsis — never a chopped word."""
        if not text or q.fontMetrics().horizontalAdvance(text) <= max_w:
            return text
        cut = text
        while cut and q.fontMetrics().horizontalAdvance(cut + "…") > max_w:
            cut = cut[:-1]
            if " " in cut:
                cut = cut[:cut.rfind(" ")]
        return (cut.rstrip() + "…") if cut else ""

    def _hit(self, pos) -> int:
        for i, (rect, *_rest) in enumerate(self._strand_rects()):
            if rect.contains(QPointF(pos)):
                return i
        return -1

    def mouseMoveEvent(self, event) -> None:                     # noqa: N802
        over = self._hit(event.position())
        if over != self._hover:
            self._hover = over
            self.setCursor(Qt.CursorShape.PointingHandCursor if over >= 0
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event) -> None:                         # noqa: N802
        if self._hover != -1:
            self._hover = -1
            self.update()

    def mousePressEvent(self, event) -> None:                     # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            i = self._hit(event.position())
            if i >= 0:
                _rect, label, _why, target = self._strand_rects()[i]
                self.set_status(f"OPENING {label}")
                self.app_requested.emit(target)
                return
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:                        # noqa: N802
        super().resizeEvent(event)
        self._place_dock()

    def _place_dock(self) -> None:
        """Sit the dock on the right, clear of the reactor and the app grid."""
        if not hasattr(self, "dock"):
            return
        w, h = self.width(), self.height()
        width = self.dock.width() or min(560, int(w * 0.42))
        self.dock.setFixedWidth(width)
        height = min(int(h * 0.62), 560)
        self.dock.setFixedHeight(height)
        self.dock.move(max(8, w - width - 28), max(8, int(h * 0.10)))
        self.dock.raise_()

    def open_app(self, target: str) -> bool:
        """True when the deck handled it itself (the dock), False for a real Windows app."""
        if target.startswith("dock:"):
            self.dock.open(target.split(":", 1)[1])
            self.dock.raise_()
            self.set_status("OPENED INSIDE JARVIS")
            return True
        return False

    def _poll_work(self) -> None:
        """Read the activity record; repaint only if it says something new."""
        try:
            snap = _activity.activity().snapshot()
        except Exception:                                        # noqa: BLE001
            return
        strokes = int(snap.get("strokes") or 0)
        if strokes == self._strokes:
            return
        self._strokes = strokes
        self._work = list(snap.get("history") or [])[-6:]
        # `live` is "label · note"; `request` is the sentence the person actually said.
        live = str(snap.get("live") or "").strip()
        request = str(snap.get("request") or "").strip()
        elapsed = float(snap.get("elapsed") or 0.0)
        if snap.get("busy") and live:
            self._now = f"{live} · {elapsed:.1f} s" if elapsed else live
        else:
            self._now = ""
        state = str(snap.get("state") or "")
        head = request if request else (self._now or state)
        self._status = ("JARVIS · " + head).upper()[:60]
        self.update()

    def note_work(self, line: str) -> None:
        """Say one thing that is happening, from anywhere in the app."""
        self._now = (line or "").strip()[:80]
        self._status = ("JARVIS · " + self._now).upper()[:60]
        self.update()

    # -- geometry --------------------------------------------------------
    def show_fullscreen(self) -> None:
        screens = QGuiApplication.screens()
        if screens:
            # cover the whole virtual desktop so every monitor is ARC
            geo = screens[0].geometry()
            for s in screens[1:]:
                geo = geo.united(s.geometry())
            self.setGeometry(geo)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(80, self.input.setFocus)

    def set_exit_phrase(self, phrase: str) -> None:
        self._exit_phrase = phrase
        self.update()

    def set_status(self, text: str) -> None:
        self._status = text
        self.update()

    def set_opening(self, text: str) -> None:
        """A big, centred answer to the click — not a corner label.

        The report behind this: *"yethavathu task click pana process aaga matiku,
        appadiyae hang aagi nikkithu"*. The old deck changed a status word at the bottom
        of a 1080p fullscreen picture, which nobody sees, so a click that WORKED looked
        identical to a click that was ignored. This draws the sentence in the middle of
        the web, and `clear_opening()` takes it away.
        """
        self._opening = (text or "").strip()[:70]
        self.update()

    def clear_opening(self) -> None:
        self._opening = ""
        self.update()

    def status_text(self) -> str:
        """What the deck is saying right now — read by the tests, and by the tray tooltip."""
        return str(getattr(self, "_status", ""))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        if self._holo is not None:
            self._holo.set_theme(theme)
        self.setStyleSheet(self._qss(theme))
        self.update()

    # -- behaviour -------------------------------------------------------
    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        low = text.lower()
        if self._exit_phrase and self._exit_phrase in low:
            if getattr(self, "dock", None) is not None and self.dock.isVisible():
                self.dock.close_panel()      # Esc closes the panel, not the whole workspace
                return
            self.exit_requested.emit()
            return
        self.command.emit(text)

    def _on_tick(self, dt: float) -> None:
        if not self.isVisible():
            return
        self._t += dt
        # A full-screen hologram is the most expensive thing this app draws. Under load
        # it steps down its own resolution and repaints on every other frame: half the
        # cost, and on a moving background nobody can tell.
        try:
            stats = ticker().stats()
            load = float(stats.get("load") or 0.0)
        except Exception:                                        # noqa: BLE001
            load = 0.0
        if self._holo is not None:
            self._holo.note_load(load)
        self._skip = not getattr(self, "_skip", False) if load > 0.75 else False
        if self._skip:
            return
        if self._holo is not None:
            self._holo.step(dt)
        self.update()

    def advance(self, seconds: float) -> None:
        self._t += seconds
        if self._holo is not None:
            self._holo.step(seconds)
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if getattr(self, "dock", None) is not None and self.dock.isVisible():
                self.dock.close_panel()      # Esc closes the panel, not the whole workspace
                return
            self.exit_requested.emit()
        else:
            super().keyPressEvent(event)

    # -- the picture -----------------------------------------------------
    def _paint_web(self, q: QPainter, w: int, h: int, th: Theme) -> None:
        """JARVIS in the middle, six strands, six plain sentences.

        Nothing here is decoration for its own sake: every line is a thing that can be
        clicked, and every box carries the sentence that says what clicking it does. The
        old screen had a globe, a clock and six unlabelled tiles, and the honest report
        was "ena nadakuthu nay enakku puriyala".
        """
        import math as _m
        accent = th.q("accent")
        accent2 = th.q("accent2")
        cx, cy, rx, ry = self._web_geometry()
        strands = self._strand_rects()

        # ---- the web itself: spokes, then two rings between neighbours ------
        for rect, _label, _why, _target in strands:
            q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 120), 1.6))
            q.drawLine(QPointF(cx, cy), QPointF(rect.center().x(), rect.center().y()))
        ring_on = QColor(accent.red(), accent.green(), accent.blue(), 55)
        q.setPen(QPen(ring_on, 1.0, Qt.PenStyle.DotLine))
        for factor in (0.52, 0.80):
            q.drawEllipse(QPointF(cx, cy), rx * factor, ry * factor)
        # the acknowledgement card is drawn LAST (see the end of paintEvent) so nothing
        # can cover it: a click must never look like nothing happened.

        # a faint line between neighbouring strands: that is what makes it a web
        q.setPen(QPen(QColor(accent2.red(), accent2.green(), accent2.blue(), 60), 1.0))
        pts = [rect.center() for rect, *_ in strands]
        for i in range(len(pts)):
            q.drawLine(pts[i], pts[(i + 1) % len(pts)])

        # ---- the centre: JARVIS, and the one line that matters --------------
        core_r = min(132.0, max(64.0, min(w, h) * 0.105))
        halo = QRadialGradient(QPointF(cx, cy), core_r * 1.9)
        halo.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 70))
        halo.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(halo)
        q.drawEllipse(QPointF(cx, cy), core_r * 1.9, core_r * 1.9)

        busy = bool(self._now)
        pulse = 1.0 + (0.035 * _m.sin(self._t * 2.4) if busy else 0.0)
        q.setBrush(QColor(3, 14, 20, 235))
        q.setPen(QPen(accent, 2.0))
        q.drawEllipse(QPointF(cx, cy), core_r * pulse, core_r * pulse)
        q.setPen(QPen(QColor(accent2.red(), accent2.green(), accent2.blue(), 90), 1.0))
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.drawEllipse(QPointF(cx, cy), core_r * 1.28, core_r * 1.28)

        f = QFont("Segoe UI", 1)
        f.setPixelSize(int(core_r * 0.30))
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.6)
        q.setFont(f)
        q.setPen(QColor(th.text))
        fm = q.fontMetrics()
        q.drawText(QPointF(cx - fm.horizontalAdvance("JARVIS") / 2,
                           cy + f.pixelSize() * 0.32), "JARVIS")

        # "what is it doing" sits just UNDER the circle: inside it there was room for
        # about four letters ("TOOL…"), which is not an answer to anything.
        f2 = QFont("Segoe UI", 1)
        f2.setPixelSize(max(11, int(core_r * 0.20)))
        q.setFont(f2)
        q.setPen(QColor(accent) if busy else QColor(th.dim).lighter(150))
        line = self._fit(q, (self._now or "idle — nothing running right now").upper(),
                         min(620.0, core_r * 6.2))
        fm2 = q.fontMetrics()
        q.drawText(QPointF(cx - fm2.horizontalAdvance(line) / 2,
                           cy + core_r + f2.pixelSize() * 1.9), line)

        # ---- the six strands ----------------------------------------------
        for i, (rect, label, why, _target) in enumerate(strands):
            hot = (i == self._hover)
            q.setBrush(QColor(accent.red(), accent.green(), accent.blue(),
                              215 if hot else 40))
            q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(),
                                 255 if hot else 140), 1.4))
            q.drawRoundedRect(rect, 12, 12)

            fl = QFont("Segoe UI", 1)
            fl.setPixelSize(max(10, int(rect.width() * 0.085)))
            fl.setWeight(QFont.Weight.Bold)
            fl.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
            q.setFont(fl)
            q.setPen(QColor("#04090f") if hot else QColor(th.text))
            q.drawText(QRectF(rect.x() + 10, rect.y() + 8, rect.width() - 20, 18),
                       int(Qt.AlignmentFlag.AlignHCenter), label)

            fw = QFont("Segoe UI", 1)
            fw.setPixelSize(max(8, int(rect.width() * 0.056)))
            q.setFont(fw)
            q.setPen(QColor("#04090f") if hot else QColor(th.dim).lighter(160))
            words = self._fit(q, why, rect.width() - 18)
            q.drawText(QRectF(rect.x() + 8, rect.y() + 27, rect.width() - 16, 20),
                       int(Qt.AlignmentFlag.AlignHCenter), words)

    def _paint_recent(self, q: QPainter, w: int, h: int, th: Theme) -> None:
        """The last few finished steps, bottom left, with the time each one took.

        Read straight from the activity record, so it cannot show work that did not
        happen. Empty means empty: "no steps yet" rather than a decoration.
        """
        pad = 30
        x = pad
        y = h * 0.775
        accent = th.q("accent")
        f = QFont("Segoe UI", 1)
        f.setPixelSize(9)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
        q.setFont(f)
        q.setPen(QPen(accent))
        q.drawText(QPointF(x, y), "WHAT JARVIS HAS DONE")
        y += 18
        f2 = QFont("Segoe UI", 1)
        f2.setPixelSize(10)
        q.setFont(f2)
        rows = self._work[-4:]
        if not rows:
            q.setPen(QColor(th.dim).lighter(140))
            q.drawText(QPointF(x, y), "no steps yet — ask it something")
            return
        for row in rows:
            text = self._fit(q, row if isinstance(row, str) else str(row), w * 0.42)
            q.setPen(QColor(th.dim).lighter(160))
            q.drawText(QPointF(x, y), "· " + text)
            y += 16

    def paintEvent(self, event) -> None:  # noqa: N802
        th = self._theme
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        # A plain, dark surface. The hologram globe used to be painted here on every
        # frame; the web says the same thing about the app and costs almost nothing -
        # which is also the answer to "lag aagavey koodathu".
        grad = QLinearGradient(0, 0, w * 0.35, h)
        grad.setColorAt(0.0, QColor(th.panel))
        grad.setColorAt(0.6, QColor(th.bg))
        grad.setColorAt(1.0, QColor(th.bg).darker(115))
        q.fillRect(0, 0, w, h, grad)

        self._paint_web(q, w, h, th)
        self._paint_recent(q, w, h, th)

        accent = th.q("accent")

        # ---- status + what this screen IS ---------------------------------
        f3 = QFont("Segoe UI", 1)
        f3.setPixelSize(max(9, int(min(w, h) * 0.012)))
        f3.setWeight(QFont.Weight.Bold)
        f3.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.0)
        q.setFont(f3)
        q.setPen(accent)
        fm3 = q.fontMetrics()
        q.drawText(QPointF(w * 0.5 - fm3.horizontalAdvance(self._status) / 2, h * 0.05),
                   self._status)

        f4 = QFont("Segoe UI", 1)
        f4.setPixelSize(max(9, int(min(w, h) * 0.0115)))
        q.setFont(f4)
        q.setPen(QColor(th.dim).lighter(140))
        why = ("this is one full-screen window of JARVIS — six strands, one thing each. "
               "your Windows underneath is untouched")
        fm4 = q.fontMetrics()
        q.drawText(QPointF(w * 0.5 - fm4.horizontalAdvance(why) / 2, h * 0.083), why)

        hint = f'CLICK A STRAND  ·  TYPE BELOW  ·  SAY "{self._exit_phrase.upper()}"  ·  ESC = BACK TO NORMAL'
        fm5 = q.fontMetrics()
        q.drawText(QPointF(w * 0.5 - fm5.horizontalAdvance(hint) / 2, h * 0.955), hint)

        # ---- corner brackets ----------------------------------------------
        q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 110), 2.0))
        pad2, arm = 26, 52
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            x = pad2 if sx > 0 else w - pad2
            y = pad2 if sy > 0 else h - pad2
            q.drawLine(QPointF(x, y), QPointF(x + sx * arm, y))
            q.drawLine(QPointF(x, y), QPointF(x, y + sy * arm))

        # ---- what the last click is doing (drawn over everything) ----------
        if self._opening:
            q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 210), 2.0))
            card = QRectF(w * 0.5 - 250, h * 0.5 - 34, 500, 68)
            q.setBrush(QColor(8, 12, 20, 225))
            q.drawRoundedRect(card, 16, 16)
            q.setPen(QColor(accent.red(), accent.green(), accent.blue(), 255))
            font = q.font()
            font.setPointSize(max(11, min(20, int(h * 0.020))))
            font.setBold(True)
            q.setFont(font)
            q.drawText(card, Qt.AlignmentFlag.AlignCenter, self._opening.upper())
        q.end()

    # -- style -----------------------------------------------------------
    def _qss(self, th: Theme) -> str:
        return f"""
            QPushButton#magicApp {{
                color: {th.accent}; background: rgba(0,0,0,0.30);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 14px; font-size: 11px; font-weight: 700;
                letter-spacing: 2.2px;
            }}
            QPushButton#magicApp:hover {{
                color: #04090f; background: {th.accent}; border-color: {th.accent};
            }}
            QLineEdit#magicInput {{
                background: rgba(0,0,0,0.45); color: {th.text};
                border: 1px solid rgba(255,255,255,0.16);
                border-radius: 22px; padding: 9px 20px; font-size: 13.5px;
                selection-background-color: {th.accent};
            }}
            QLineEdit#magicInput:focus {{ border-color: {th.accent}; }}
        """
