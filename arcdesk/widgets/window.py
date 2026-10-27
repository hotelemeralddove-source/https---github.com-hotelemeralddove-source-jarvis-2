"""The JARVIS Control Center window.

Lean choices baked in:
  * Frameless, self-painted background -> no native chrome, no theme fights.
  * Cards are plain QFrame + one stylesheet string (rebuilt only on mode change).
  * The dashboard and the assistant console live in a QStackedWidget, so the
    console costs nothing while you are not using it.
  * All AI work happens on worker threads; the GUI thread only paints.
"""
from __future__ import annotations

import os
import subprocess

from .. import quiet
import threading
import time
from pathlib import Path

from PySide6.QtCore import (QEvent, QEventLoop, QObject, QPoint, QRectF, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
import shiboken6

from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .. import companion_voice, config, guard, sfx
from ..ai import tools
from ..ai.mcp import MCPManager
from ..ai.agent import Agent
from ..ai.persona import machine_brief
from ..ai.voice import Voice
from ..charms import Charm, CharmsOverlay
from ..magic import MagicController, render_wallpaper
from ..stats import SystemSampler, fmt_gb
from ..theme import THEMES, Theme, get_theme, next_mode, tuned
from ..ticker import ticker
from ..weather import WeatherService
from ..hotkeys import HotkeyListener
from ..wake.client import WakeServer
from ..wake.daemon_runner import DaemonRunner
from .aisetup import AISetupDialog
from .assistant import AssistantConsole
from .awakening import Awakening
from .palette import CommandPalette
from .magicscreen import MagicScreen
from .settings import SettingsDialog
from .companion import IDLE, LISTENING, SPEAKING, THINKING, Companion
from .gauge import ArcGauge
from .hud import ClockCard, ModeBar
from .reactor import ArcReactor
from .shortcuts import Card, ShortcutShelf

HINT_IDLE = "READY · CTRL+J CONSOLE · CTRL+SPACE ASK · ESC CLOSE"


def _rgba(hexs: str, alpha: float) -> str:
    c = QColor(hexs)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha:.2f})"


def _label(text: str, obj: str, px: int, spacing: float = 0.0,
           weight: QFont.Weight = QFont.Weight.Medium) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName(obj)
    f = lb.font()
    f.setPixelSize(px)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    lb.setFont(f)
    return lb


class UiBridge(QObject):
    """Lets worker-thread tools ask the GUI to do something, safely."""
    request_mode = Signal(str)
    request_timer = Signal(int, str)
    request_charms = Signal(bool)
    request_magic = Signal(str)
    request_art = Signal(object)   # a sketch to put on the easel
    request_photo = Signal(str, str)   # a real photograph (path, caption)


#: What a launched Windows app calls its window, so it can be raised after a click in
#: magic mode. Only the ones the deck offers by name need to be here.
_APP_TITLES = {
    "settings": "Settings",
    "explorer": "File Explorer",
    "notepad": "Notepad",
    "calc": "Calculator",
    "taskmgr": "Task Manager",
}


class MainWindow(QWidget):
    _heard = Signal(str)          # speech-to-text result, from a worker thread
    _mic_state = Signal(str)
    summon_requested = Signal()   # another launch asked this copy to come forward

    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self.cfg = cfg
        self.theme: Theme = tuned(cfg.get("mode", "chill"), cfg.get("effects"))
        self.sampler = SystemSampler()
        self.weather = WeatherService(self)
        self.weather.updated.connect(self._on_weather)
        self._drag: QPoint | None = None
        self._timers: list[QTimer] = []
        self._tray = None
        self._speech_open = False
        self._session_start = time.time()
        self._nudge_timer = QTimer(self)
        self._nudge_timer.setInterval(5 * 60 * 1000)
        self._nudge_timer.timeout.connect(self._check_nudge)
        if cfg.get("ai", {}).get("nudges", False):
            self._nudge_timer.start()
        self._console_open = False

        # --- wake word ---------------------------------------------------
        wcfg = cfg.get("wake", {})
        self.wake_daemon = DaemonRunner()
        self.wake_server = WakeServer(int(wcfg.get("port", 8765)), self)
        self.wake_server.woke.connect(self._on_wake)
        self.wake_server.snoozed.connect(self._on_exit_phrase)
        self.wake_server.command.connect(self._on_wake_command)
        self.wake_server.status.connect(self._on_wake_status)
        self.wake_server.failed.connect(self._on_wake_failed)
        self.wake_server.barged.connect(self._on_barge)


        # --- AI wiring ---------------------------------------------------
        self.voice = Voice(cfg)
        self.agent = Agent(cfg, self)
        self.agent.context_fn = lambda: machine_brief(
            self.sampler.cpu, self.sampler.ram, self.theme.key)
        self.agent.reply.connect(self._on_reply)
        self.agent.speak_partial.connect(self._on_speak_partial)
        self.agent.speak_end.connect(self._on_speak_end)
        self.agent.thinking.connect(self._on_thinking)
        self.agent.tool_used.connect(self._on_tool)
        self.agent.error.connect(self._on_ai_error)
        self.agent.needs_confirm.connect(self._on_confirm)
        self.agent.brain_changed.connect(self._on_brain)
        self.bridge = UiBridge(self)
        self.bridge.request_mode.connect(self.set_mode)
        self.bridge.request_timer.connect(self.add_timer)
        self.bridge.request_charms.connect(self.show_charms)
        self.bridge.request_magic.connect(self._on_magic_request)
        self.bridge.request_art.connect(self._on_request_art)
        self.bridge.request_photo.connect(self._on_request_photo)
        tools.bind_host(self.bridge)

        # --- open-source tool servers (MCP) ------------------------------
        self.mcp = MCPManager()
        mcfg = cfg.get("mcp", {})
        if mcfg.get("enabled", True) and mcfg.get("servers"):
            self.mcp.load(mcfg["servers"])
            threading.Thread(target=self._boot_mcp, daemon=True,
                             name="arc-mcp-boot").start()

        # --- shadow mode / hotkeys / palette ----------------------------
        scfg = cfg.get("shadow", {})
        self.shadow = bool(scfg.get("enabled", False)
                           or cfg.get("_stealth_this_launch")) \
            and not cfg.get("_force_show")
        self._awakening = None
        self._last_question = ""        # kept for the vault's checkpoint
        self.palette = CommandPalette(self.theme)
        self.palette.submitted.connect(self.ask)
        self.agent.reply.connect(self._palette_reply)
        self.agent.tool_used.connect(self._palette_tool)
        self.agent.error.connect(self._palette_error)
        self.agent.brain_changed.connect(lambda _l="": self.palette.set_brain(self.agent.describe()))
        self.hotkeys = HotkeyListener({
            "palette": str(scfg.get("hotkey_palette", "ctrl+alt+j")),
            "quit": str(scfg.get("hotkey_quit", "ctrl+alt+q")),
        }, self)
        self.hotkeys.triggered.connect(self._on_hotkey)

        # --- gravity charms ---------------------------------------------
        ccfg = cfg.get("charms", {})
        try:
            self._charm_items = [Charm.from_dict(d) for d in (ccfg.get("items") or [])]
        except Exception:
            self._charm_items = []
        self.overlay = CharmsOverlay(self.theme, self._charm_items)
        self.overlay.changed.connect(self._on_charms_changed)
        self.overlay.edit_mode_changed.connect(self._on_charms_edit)

        # --- magic mode ---------------------------------------------------
        self.magic = MagicController()
        self._magic_screen: MagicScreen | None = None
        self._holo_window = None
        self.magic_active = False
        self.hotkeys.failed.connect(self._on_hotkey_failed)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Arc Desk")
        # A floor, not a size. 840x570 was wider than the usable width of a 1366-pixel
        # laptop at 125% scaling, so the window hung off the right edge and could not be
        # made smaller. clamp_to_screen() lowers this further if the display is smaller.
        self.setMinimumSize(560, 420)

        self._build()
        self._restore_geometry()
        from .fit import add_size_grip, clamp_to_screen
        clamp_to_screen(self)
        self._grip = add_size_grip(self)

        # Esc must work no matter which child has the keyboard focus — that was the
        # complaint ("esc kodutha close aaga matiku"). A widget-level keyPressEvent is
        # not enough: the chat field, the transcript and the palette all eat keys, and
        # a frameless window does not always hold the focus ring. One application-wide
        # filter, installed once, decides for all of them.
        # The filter is on THIS window, not on the application. Qt walks the parent
        # chain for filters, so this sees every child — the chat field, the dialogs,
        # the quick menu — which is all Esc needs. What it does NOT see are events
        # delivered to windows outside this tree, and those are exactly the ones that
        # are dead: the crash report showed this filter dying on an event whose window
        # Qt itself had already abandoned ("No Qt Window found for event 0x46", a minute
        # of it, then an access violation on the next dispatch). Windows keeps sending
        # messages to destroyed hwnds; an application-level filter meets them, a
        # window-level one never does.
        self.installEventFilter(self)
        # Belt AND braces. An event filter only sees keys that reach the application's
        # own widgets; a QShortcut with ApplicationShortcut context is delivered by Qt
        # even when the focus sits in the chat field, in a list, or in a menu. The user
        # pressed Esc twice and nothing happened, so this no longer relies on one
        # mechanism.
        try:
            from PySide6.QtGui import QKeySequence, QShortcut
            self._esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
            self._esc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            self._esc.setAutoRepeat(False)
            self._esc.activated.connect(self.escape_pressed)
            self._hide_shortcut = QShortcut(QKeySequence("Ctrl+Alt+H"), self)
            self._hide_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            self._hide_shortcut.activated.connect(self.hide)
        except Exception:
            self._esc = None
        self._esc_hint_shown = False
        self._last_esc = 0.0
        # STOP in the console is the same action as the Esc path, and the agent's
        # step announcements drive the console's process strip
        self.console.stop_requested.connect(self.cancel_current)
        self.agent.step_started.connect(self.console.step_running)
        self.agent.step_finished.connect(self.console.step_done)

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(1000)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start()

        self._guard_timer = QTimer(self)
        self._guard_timer.setInterval(10_000)
        self._guard_timer.timeout.connect(self._apply_guards)
        self._guard_timer.start()

        # reminders and focus blocks: 15 s resolution, so a reminder is never late
        # by more than a quarter of a minute and never announces itself twice
        self._day_timer = QTimer(self)
        self._day_timer.setInterval(15_000)
        self._day_timer.timeout.connect(self._check_day)
        self._day_timer.start()
        self._guard_reason = ""
        self._status_checked = 0.0        # throttles the TCP probe in the status card
        # The acknowledgement is only spoken when a request is genuinely slow (1.2 s).
        # A Lite answer in 4 ms does not need "on it, commander" in front of it.
        self._ack_timer = QTimer(self)
        self._ack_timer.setSingleShot(True)
        self._ack_timer.setInterval(1200)
        self._ack_timer.timeout.connect(self._say_ack)
        self._pending_request = ""
        self._opened_at = 0.0            # the last time ARC said hello (see _cinematic_open)

        self._heard.connect(self._on_heard)
        self._mic_state.connect(self._on_mic_state)

        self.apply_theme()
        self._apply_guards()
        self._refresh_stats()
        self._on_brain(self.agent.describe())
        if self.cfg.get("magic", {}).get("restore_on_start", True):
            healed = self.magic.restore_if_needed()
            if healed:
                self.console.add_note("MAGIC · " + healed)
        self._wake_boot()
        self.palette.set_brain(self.agent.describe())
        if scfg.get("hotkeys", True):
            self.hotkeys.start()
        if ccfg.get("enabled", False):
            self.show_charms(True)

        if self.cfg["weather"].get("enabled"):
            w = self.cfg["weather"]
            self.weather.refresh(w["lat"], w["lon"], w.get("city", ""),
                                 int(w.get("refresh_min", 20)))

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(12)

        # ---- header ----------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(12)
        brand = _label("JARVIS DESK", "brand", 15, 5.0, QFont.Weight.Bold)
        brand.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        sub = _label("YOUR DESKTOP · YOUR UNIVERSE", "sub", 9, 2.6)
        sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header.addWidget(brand)
        header.addWidget(sub)
        header.addStretch(1)

        self.mode_chip = _label("", "chip", 9, 2.2, QFont.Weight.DemiBold)
        header.addWidget(self.mode_chip)

        self.wake_pill = QPushButton("WAKE OFF")
        self.wake_pill.setObjectName("wakePill")
        self.wake_pill.setFixedHeight(24)
        self.wake_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wake_pill.setToolTip("Wake word: click to enable / disable")
        self.wake_pill.clicked.connect(self.toggle_wake)
        header.addWidget(self.wake_pill)

        self.btn_ask = QPushButton("ASK JARVIS ▸")
        self.btn_ask.setObjectName("askBtn")
        self.btn_ask.setFixedHeight(26)
        self.btn_ask.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ask.setToolTip("Open the JARVIS console (Ctrl+J)")
        self.btn_ask.clicked.connect(self.toggle_console)
        header.addWidget(self.btn_ask)

        self.btn_menu = QPushButton("⋯")
        self.btn_menu.setObjectName("ghost")
        self.btn_menu.setFixedSize(28, 26)
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.setToolTip("Quick settings")
        self.btn_menu.clicked.connect(self._show_quick_menu)
        header.addWidget(self.btn_menu)

        self.btn_min = QPushButton("–")
        self.btn_min.setObjectName("ghost")
        self.btn_min.setFixedSize(28, 26)
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.setToolTip("Minimize to the taskbar (the reactor keeps running)")
        self.btn_min.clicked.connect(self.showMinimized)
        header.addWidget(self.btn_min)

        self.btn_max = QPushButton("▢")
        self.btn_max.setObjectName("ghost")
        self.btn_max.setFixedSize(28, 26)
        self.btn_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_max.setToolTip("Expand to fill the screen / back to a window")
        self.btn_max.clicked.connect(self.toggle_maximized)
        header.addWidget(self.btn_max)

        self.btn_tray = QPushButton("⌄")
        self.btn_tray.setObjectName("ghost")
        self.btn_tray.setFixedSize(28, 26)
        self.btn_tray.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tray.setToolTip("Hide to the tray (Esc does the same)")
        self.btn_tray.clicked.connect(self.hide)
        header.addWidget(self.btn_tray)
        root.addLayout(header)

        # ---- body ------------------------------------------------------
        body = QHBoxLayout()
        body.setSpacing(18)
        root.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(2)
        self.reactor = ArcReactor(self.theme)
        self.reactor.setFixedSize(330, 330)
        self.reactor.installEventFilter(self)
        left.addStretch(1)
        left.addWidget(self.reactor, 0, Qt.AlignmentFlag.AlignHCenter)
        hint = _label("CLICK CORE · CYCLE MODE", "hint", 9, 2.4)
        hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        left.addWidget(hint)

        self.companion = Companion(self.theme)
        self.companion.clicked.connect(self.toggle_console)
        left.addWidget(self.companion, 0, Qt.AlignmentFlag.AlignHCenter)
        left.addStretch(0)
        body.addLayout(left, 0)

        # ---- right: dashboard <-> console -------------------------------
        right = QVBoxLayout()
        right.setSpacing(0)
        body.addLayout(right, 1)

        self.stack = QStackedWidget()
        self.stack.setObjectName("stack")
        right.addWidget(self.stack, 1)

        # -- dashboard page
        dash = QWidget()
        dl = QVBoxLayout(dash)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(12)

        clock_card = QFrame()
        clock_card.setObjectName("card")
        cl = QVBoxLayout(clock_card)
        cl.setContentsMargins(20, 12, 20, 14)
        self.clock = ClockCard(self.theme)
        cl.addWidget(self.clock)
        dl.addWidget(clock_card)

        sys_card = QFrame()
        sys_card.setObjectName("card")
        sl = QHBoxLayout(sys_card)
        sl.setContentsMargins(18, 14, 18, 14)
        sl.setSpacing(10)
        self.gauge_cpu = ArcGauge("CPU")
        self.gauge_ram = ArcGauge("RAM")
        sl.addWidget(self.gauge_cpu)
        sl.addWidget(self.gauge_ram)
        info = QVBoxLayout()
        info.setSpacing(6)
        self.lbl_mem = _label("", "stat", 10, 1.6)
        self.lbl_cores = _label("", "stat", 10, 1.6)
        self.lbl_foot = _label("", "stat", 10, 1.6)
        info.addStretch(1)
        info.addWidget(self.lbl_mem)
        info.addWidget(self.lbl_cores)
        info.addWidget(self.lbl_foot)
        info.addStretch(1)
        sl.addLayout(info, 1)
        dl.addWidget(sys_card)

        self.shelf = ShortcutShelf(self.cfg.get("shortcuts") or [])
        self.shelf.status.connect(self._on_status)
        dl.addWidget(Card(self.shelf))

        # The right column used to be half empty under the shortcuts. This is the one
        # card that answers the three questions the user actually asked, in the place
        # they look: what thinks, can it hear, and whose voice answers.
        status_card = QFrame()
        status_card.setObjectName("card")
        stl = QVBoxLayout(status_card)
        stl.setContentsMargins(18, 12, 18, 12)
        stl.setSpacing(5)
        self.lbl_brain = _label("", "stat", 10, 1.6)
        self.lbl_ears = _label("", "stat", 10, 1.6)
        self.lbl_voice = _label("", "stat", 10, 1.6)
        for w in (self.lbl_brain, self.lbl_ears, self.lbl_voice):
            stl.addWidget(w)
        dl.addWidget(status_card)
        dl.addStretch(1)

        self.mode_bar = ModeBar()
        self.mode_bar.mode_changed.connect(self.set_mode)
        dl.addWidget(self.mode_bar)

        self.lbl_ready = _label(HINT_IDLE, "hint", 9, 2.0)
        dl.addWidget(self.lbl_ready)
        self.stack.addWidget(dash)

        # -- console page
        self.console = AssistantConsole()
        self.console.submitted.connect(self.ask)
        self.console.mic_requested.connect(self.listen_once)
        self.console.settings_requested.connect(self.open_ai_setup)
        self.console.reset_requested.connect(self._reset_chat)
        self.console.replay_requested.connect(
            lambda: self.voice.speak(self.console.last_answer))
        self.stack.addWidget(self.console)

    # -------------------------------------------------------------- theme
    def apply_theme(self) -> None:
        th = self.theme
        base = int(self.cfg.get("fps_cap") or th.fps)
        fps, reason = guard.desired_fps(base)
        self._guard_reason = reason
        ticker().set_fps(fps)
        ticker().set_paused(not self.cfg.get("animations", True))

        self.reactor.set_theme(th)
        self.reactor.set_effects(th.effects)
        self.clock.set_theme(th)
        self.companion.set_theme(th)
        self.gauge_cpu.set_theme(th, "accent")
        self.gauge_ram.set_theme(th, "accent2")
        self.mode_bar.set_mode(th.key)
        self.mode_chip.setText(f"{th.label.upper()} · {th.hint.upper()}")
        self.palette.set_theme(th)
        self.overlay.set_theme(th)
        if self._magic_screen is not None:
            self._magic_screen.set_theme(th)
        if self._holo_window is not None:
            self._holo_window.set_theme(th)
        self.console.setStyleSheet(self.console.styles(th))
        self.console.apply_doc_style(th)

        self.setStyleSheet(f"""
            QWidget {{ color: {th.text};
                       font-family: 'Segoe UI', 'Inter', 'Noto Sans', sans-serif; }}
            QLabel#brand {{ color: {th.text}; }}
            QLabel#sub {{ color: {QColor(th.dim).lighter(145).name()}; }}
            QLabel#chip {{ color: {th.accent};
                           border: 1px solid {_rgba(th.accent, 0.40)};
                           border-radius: 10px; padding: 3px 10px;
                           background: {_rgba(th.accent, 0.07)}; }}
            QLabel#hint {{ color: {QColor(th.dim).lighter(135).name()}; }}
            QLabel#stat {{ color: {QColor(th.dim).lighter(150).name()}; }}
            QFrame#card {{ background: {_rgba(th.accent, 0.055)};
                           border: 1px solid {_rgba(th.accent, 0.18)};
                           border-radius: 16px; }}
            QPushButton#ghost {{ color: {QColor(th.dim).lighter(150).name()};
                                 background: transparent; border: none;
                                 border-radius: 8px; font-size: 14px; }}
            QPushButton#ghost:hover {{ color: {th.accent};
                                       background: {_rgba(th.accent, 0.12)}; }}
            QPushButton#askBtn {{ color: {th.accent};
                                  background: {_rgba(th.accent, 0.10)};
                                  border: 1px solid {_rgba(th.accent, 0.38)};
                                  border-radius: 10px; padding: 2px 12px;
                                  font-size: 9.5px; font-weight: 700;
                                  letter-spacing: 1.6px; }}
            QPushButton#askBtn:hover {{ background: {_rgba(th.accent, 0.22)};
                                        border-color: {th.accent}; }}
            QPushButton#wakePill {{ color: {QColor(th.dim).lighter(160).name()};
                                    background: transparent;
                                    border: 1px solid {_rgba(th.dim, 0.45)};
                                    border-radius: 9px; padding: 1px 9px;
                                    font-size: 8.5px; font-weight: 700;
                                    letter-spacing: 1.3px; }}
            QPushButton#wakePill[on="true"] {{ color: {th.accent2};
                                               border-color: {_rgba(th.accent2, 0.65)};
                                               background: {_rgba(th.accent2, 0.12)}; }}
            QPushButton#wakePill:hover {{ color: {th.accent}; border-color: {th.accent}; }}
            QPushButton#pill {{ color: {QColor(th.dim).lighter(160).name()};
                                background: transparent;
                                border: 1px solid {_rgba(th.dim, 0.55)};
                                border-radius: 13px; padding: 6px 16px;
                                font-size: 10px; font-weight: 600; }}
            QPushButton#pill:hover {{ color: {th.accent};
                                      border-color: {_rgba(th.accent, 0.65)}; }}
            QPushButton#pill:checked {{ color: #04090f; background: {th.accent};
                                        border: 1px solid {th.accent}; }}
            QPushButton#tile {{ color: {QColor(th.dim).lighter(165).name()};
                                background: {_rgba(th.accent, 0.075)};
                                border: 1px solid {_rgba(th.accent, 0.20)};
                                border-radius: 11px; padding: 12px 6px;
                                font-size: 10px; font-weight: 600;
                                letter-spacing: 1.4px; }}
            QPushButton#tile:hover {{ color: {th.accent};
                                      background: {_rgba(th.accent, 0.16)};
                                      border-color: {_rgba(th.accent, 0.55)}; }}
            QMenu {{ background: {th.panel}; color: {th.text};
                     border: 1px solid {_rgba(th.accent, 0.35)};
                     border-radius: 10px; padding: 6px; }}
            QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 6px; }}
            QMenu::item:selected {{ background: {_rgba(th.accent, 0.20)}; }}
        """)
        self.update()

    def set_mode(self, key: str) -> None:
        if key not in THEMES:
            return
        self.theme = tuned(key, self.cfg.get("effects"))
        self.cfg["mode"] = key
        self.apply_theme()
        want = bool(self.cfg.get("charms", {}).get("enabled", False))
        if want and self.theme.effects >= 0.2:
            if not self.overlay.isVisible():
                self.overlay.show()
        elif self.overlay.isVisible():
            self.overlay.hide()
        config.save(self.cfg)

    def cycle_mode(self) -> None:
        self.set_mode(next_mode(self.theme.key))

    def set_effects(self, value: float | None) -> None:
        """Change how much glow the world draws — None follows the mode.

        This is the setting that used to be a lie: it was stored in settings.json and
        never read by anything. It now re-themes the world immediately, and turns the
        floating charms off below 0.2 (they are pure glow — at 0 they are invisible
        anyway, so hiding them also saves the compositor work).
        """
        self.cfg["effects"] = value
        self.theme = tuned(self.theme.key, value)
        self.apply_theme()
        want = bool(self.cfg.get("charms", {}).get("enabled", False))
        if want and self.theme.effects >= 0.2:
            if not self.overlay.isVisible() and self.isVisible():
                self.overlay.show()
        elif self.overlay.isVisible():
            self.overlay.hide()
        config.save(self.cfg)

    def set_animations(self, on: bool) -> None:
        self.cfg["animations"] = bool(on)
        ticker().set_paused(not on)
        self.reactor.update()
        self.companion.update()
        config.save(self.cfg)

    # -------------------------------------------------------------- stats
    def _refresh_stats(self) -> None:
        s = self.sampler
        s.sample()
        self.gauge_cpu.set_value(s.cpu)
        self.gauge_ram.set_value(s.ram)
        self.lbl_mem.setText(f"MEMORY  {fmt_gb(s.mem_used)} / {fmt_gb(s.mem_total)}")
        self.lbl_cores.setText(f"THREADS {s.cores}   ·   {ticker().fps} FPS CAP")
        voice = self.wake_daemon.rss_mb()
        st = ticker().stats()
        perf = f"{st['fps']} FPS · {st['frame_ms']:.1f} ms/frame"
        if voice:
            self.lbl_foot.setText(f"JARVIS CORE {s.self_mb:.0f} MB   ·   VOICE {voice:.0f} MB"
                                  f"   ·   {perf}")
        else:
            self.lbl_foot.setText(f"JARVIS CORE {s.self_mb:.0f} MB   ·   {perf}")
        self._refresh_status_card()
        # the honest answer to "is it doing anything?" — on the window, always
        from .. import activity as _activity
        snap = _activity.activity().snapshot()
        if snap["busy"]:
            self.lbl_ready.setText(f"● {snap['live'] or snap['state']} · "
                                   f"{snap['elapsed']:.1f} s")
        self.console.refresh_activity()

    def _refresh_status_card(self) -> None:
        """Three lines, refreshed every 10 s (a TCP probe once a second would cost more
        than the card is worth). Says what is true, including "Lite"."""
        now = time.monotonic()
        if now - self._status_checked < 10.0 and self.lbl_brain.text():
            return
        self._status_checked = now
        try:
            from .. import brain as _brain, ears as _ears, identity as _id
            st = _brain.status()
            self.lbl_brain.setText(f"BRAIN  ·  {_id.name(self.cfg)}  ·  "
                                   f"{'local model running' if st['running'] else 'Lite (offline, instant)'}")
            e = _ears.status()
            self.lbl_ears.setText("EARS   ·  " + (
                "ready — say the wake word" if e["ready"] else
                "not ready (" + ", ".join(e["rows"][k]["label"].split(" (")[0]
                                          for k in e["missing"]) + ")"))
            # cached_only: the status card ticks on the drawing thread, and a cold
            # engine cache would mean "ask every python on this PC" in the middle of it
            self.lbl_voice.setText("VOICE  ·  " + self.reply_voice_line(cached_only=True))
        except Exception as exc:
            self.lbl_brain.setText(f"STATUS unavailable: {type(exc).__name__}")

    def _apply_guards(self) -> None:
        base = int(self.cfg.get("fps_cap") or self.theme.fps)
        fps, reason = guard.desired_fps(base)
        if self.cfg.get("battery_saver", True) is False:
            fps, reason = base, ""
        # set_base_fps, not set_fps: this runs every 10 s and used to undo the ticker's
        # own slowdown, so a machine that could not afford 30 fps was pushed back to 30
        # every ten seconds — that is what "romba slow" feels like from the inside.
        ticker().set_base_fps(fps)
        if reason != self._guard_reason:
            self._guard_reason = reason
            self.lbl_ready.setText(reason or HINT_IDLE)

    def _on_weather(self, text: str, ok: bool) -> None:
        self.clock.set_weather(text, ok)

    def _on_status(self, text: str) -> None:
        self.lbl_ready.setText(text)
        if text.startswith("ASSIGNED"):
            self.cfg["shortcuts"] = self.shelf.dump()
            config.save(self.cfg)

    # ------------------------------------------------------------ console
    def toggle_console(self, force: bool | None = None) -> None:
        want = (not self._console_open) if force is None else bool(force)
        self._console_open = want
        self.stack.setCurrentIndex(1 if want else 0)
        self.btn_ask.setText("◂ DASHBOARD" if want else "ASK JARVIS ▸")
        if want:
            QTimer.singleShot(30, self.console.focus_input)
        else:
            self.setFocus()

    def reply_voice_line(self, cached_only: bool = False) -> str:
        """One line: which voice answers. Delegated so there is one wording, not two."""
        try:
            from .settings import SettingsDialog
            return SettingsDialog.reply_voice_line(self.cfg, cached_only=cached_only)
        except Exception:
            return "system voice"

    def open_settings(self) -> None:
        """Settings — opened through `safeopen`, so a fault in it cannot end the app.

        "yentha options kula ponalum auto crash mathiri close aaguthu": every option, and
        the app closes. A dialog is the one place an exception is most likely (it builds a
        hundred widgets and probes the machine while it does), and it is also the one place
        where an exception must never be fatal.
        """
        from .safeopen import open_dialog
        holder: dict = {}

        def build():
            dlg = SettingsDialog(self.cfg, self.theme, self)
            dlg.wake_test.connect(self.test_wake)
            dlg.open_brain.connect(self.open_ai_setup)
            dlg.mcp_restart.connect(self.restart_mcp)
            dlg.applied.connect(self._settings_applied)
            holder["dlg"] = dlg
            return dlg

        open_dialog("Settings", build, parent=self)

    def _settings_applied(self) -> None:
        """Re-arm the parts that changed, without needing a restart."""
        # the mode and the effects intensity live in the config, so re-derive the theme
        # before repainting — otherwise "Visual effects: Off" only took effect at restart
        self.theme = tuned(self.cfg.get("mode", self.theme.key), self.cfg.get("effects"))
        self.apply_theme()
        if self.cfg.get("wake", {}).get("enabled"):
            self._start_wake()
        else:
            self._stop_wake()
        self.hotkeys.stop()
        scfg = self.cfg.get("shadow", {})
        self.hotkeys = HotkeyListener({
            "palette": str(scfg.get("hotkey_palette", "ctrl+alt+j")),
            "quit": str(scfg.get("hotkey_quit", "ctrl+alt+q")),
        }, self)
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.hotkeys.failed.connect(self._on_hotkey_failed)
        if scfg.get("hotkeys", True):
            self.hotkeys.start()
        self.show_charms(bool(self.cfg.get("charms", {}).get("enabled", False)))
        if self.cfg.get("shadow", {}).get("tray", True) and self._tray is None:
            self.console.add_note("SETTINGS · tray icon needs a restart to appear")
        elif not self.cfg.get("shadow", {}).get("tray", True) and self._tray is not None:
            self._tray.hide()
            self._tray = None
        self.console.add_note("SETTINGS · saved")

    def open_ai_setup(self) -> None:
        from .safeopen import open_dialog

        def build():
            dlg = AISetupDialog(self.cfg, self.theme, self)
            dlg.changed.connect(self._on_ai_settings_changed)
            return dlg

        open_dialog("the AI setup", build, parent=self)

    def _on_ai_settings_changed(self) -> None:
        config.save(self.cfg)
        self.console.set_status("brain updated")
        self._on_brain("")

    def _check_nudge(self) -> None:
        """Every five minutes: is there something worth mentioning, once?"""
        try:
            from .. import nudge
            minutes = (time.time() - self._session_start) / 60
            found = nudge.check(minutes)
        except Exception:
            return
        if not found:
            return
        self.console.add_note("NUDGE · " + found["message"])
        self.companion.set_state(SPEAKING)
        self.voice.speak(found["message"])
        QTimer.singleShot(2600, lambda: self.companion.set_state(IDLE))

    def _check_day(self) -> None:
        """Say what is due: reminders that have come, focus blocks that have ended."""
        try:
            from .. import focus, reminders
        except Exception:
            return
        try:
            for item in reminders.due():
                message = f"Reminder: {item.get('text', '')}"
                self.console.add_note("REMINDER · " + str(item.get("text", "")))
                self.notify(message)
                self.companion.set_state(SPEAKING)
                self.voice.speak(message)
                QTimer.singleShot(2600, lambda: self.companion.set_state(IDLE))
        except Exception:
            pass
        try:
            done = focus.check()
            if done:
                self.console.add_note("FOCUS · " + done)
                self.notify(done)
                self.companion.set_state(SPEAKING)
                self.voice.speak(done)
                QTimer.singleShot(2600, lambda: self.companion.set_state(IDLE))
        except Exception:
            pass

    def _on_barge(self) -> None:
        """The user started talking over JARVIS — stop instantly and listen."""
        self.voice.stop()
        self._speech_open = False
        self.console.add_note("interrupted — listening")
        self.companion.set_state(THINKING)

    def _reset_chat(self) -> None:
        self.agent.reset()
        self.console.clear_view()
        self.console.add_note("conversation cleared")
        self._on_brain("")

    def ask(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self.voice.is_stop_phrase(text):
            self.voice.stop()
            self.console.add_user(text)
            self.console.add_arc("Stopped.")
            return
        self.toggle_console(True)
        self.console.add_user(text)
        self._last_question = text
        self.companion.set_state(THINKING)
        self.agent.ask(text)

    def say(self, line: str) -> None:
        """Speak a companion line through the reply voice — never raises, never waits."""
        if not (line or "").strip():
            return
        try:
            self.voice.speak(line)
            self.console.add_note("JARVIS · " + line)
        except Exception as exc:                       # noqa: BLE001
            self.console.add_note(f"VOICE · could not speak ({type(exc).__name__})")

    def _cinematic_open(self) -> None:
        """The beat when JARVIS opens, then the hello — once per opening.

        Two doors lead here: the wake word, and pressing the magic button. They can
        land within a second of each other, and the guard is what keeps that one cue
        and one sentence instead of a stutter. That was the bug: launched by hand,
        `enter_magic()` never passed through `awaken()`, so the opening beat and the
        greeting simply did not happen — the app opened in silence.
        """
        now = time.monotonic()
        if now - self._opened_at < 2.5:
            return
        self._opened_at = now
        sfx.play("magic_begin", self.cfg)
        # the greeting lands after the cinematic, not over it
        QTimer.singleShot(420, self.greet)

    def greet(self) -> None:
        """The line the whole thing is judged by: "Hi commander", in the reply voice."""
        if not companion_voice._ok(self.cfg, "greet"):   # noqa: SLF001
            return
        # the exact line that was asked for, every time: "Hi commander." A wake word
        # that answers differently each morning is a slot machine, not a companion.
        self.say(companion_voice.greeting(self.cfg))

    def _say_ack(self) -> None:
        """Fires only if the request is still running 1.2 s later."""
        from .. import activity as _activity
        if not _activity.activity().busy:
            return
        self.say(companion_voice.ack(self.cfg, self._pending_request))

    def farewell_and_close(self) -> None:
        """Say "Thank you, commander" *before* the app goes away, not after.

        Quitting immediately would cut the sentence off — which is worse than saying
        nothing, because it sounds like a fault. So: cue, line, then the action.
        """
        sfx.play("magic_end", self.cfg)
        line = companion_voice.farewell(self.cfg) \
            if companion_voice._ok(self.cfg, "farewell") else ""   # noqa: SLF001
        if line:
            self.say(line)
            QTimer.singleShot(int(900 + 55 * len(line)), self._apply_bye_action)
        else:
            self._apply_bye_action()

    def _on_thinking(self, busy: bool) -> None:
        self.console.set_busy(busy)
        if busy:
            self.console.begin_task("")
            sfx.play("task_start", self.cfg)
            self._pending_request = getattr(self.agent, "_last_request", "") or ""
            if companion_voice._ok(self.cfg, "acks"):        # noqa: SLF001
                self._ack_timer.start()
        else:
            self._ack_timer.stop()
            from .. import activity as _activity
            act = _activity.activity()
            if act.cancelled():
                sfx.play("task_failed", self.cfg, min_gap=0.3)
            elif act.state == "failed":
                sfx.play("task_failed", self.cfg, min_gap=0.3)
                if companion_voice._ok(self.cfg, "announce_done"):   # noqa: SLF001
                    self.say(companion_voice.done(self.cfg, ok=False))
            else:
                sfx.play("task_done", self.cfg)
                if companion_voice._ok(self.cfg, "announce_done"):   # noqa: SLF001
                    self.say(companion_voice.done(self.cfg))
        if not busy:
            # After the fact, show what actually ran — so "what did it do?" never
            # needs a log file. Skipped when everything happened in a blink.
            from .. import activity as _activity
            snap = _activity.activity().snapshot()
            if snap["elapsed"] >= 1.5 and snap["history"]:
                steps = [h for h in snap["history"] if not h.startswith("thinking")][-4:]
                tail = " → ".join(steps) if steps else "one quick step"
                self.console.add_step(f"{tail} · total {snap['elapsed']:.1f} s")
        if busy:
            self.companion.set_state(THINKING)
        elif self.companion._state == THINKING:  # noqa: SLF001
            self.companion.set_state(IDLE)

    def _on_reply(self, text: str) -> None:
        self._last_reply_text = text or ""
        self.console.add_arc(text)
        # ---- the vault: progress saved as it happens, not when you remember ----
        # Cheap by design: one small append into the open project, and nothing at all
        # when no project is open or the setting is off. A failed save must never
        # interrupt an answer, so it is swallowed and reported in the console only.
        try:
            if self.cfg.get("vault", {}).get("follow_answers", True):
                from .. import vault
                if vault.current():
                    vault.checkpoint(text[:600], data={"question": self._last_question[:300]})
        except Exception:
            pass
        if self._magic_screen is not None:
            self._magic_screen.set_status(text[:70].upper())
        self.companion.set_state(SPEAKING)
        QTimer.singleShot(2600, lambda: self.companion.set_state(IDLE))
        # speaking is driven by speak_partial (one sentence at a time while the
        # model is still writing), not by the finished text — see _on_speak_partial

    def _on_speak_partial(self, text: str) -> None:
        """A sentence is ready. The first one opens the mic-closed speech stream."""
        if not self.cfg.get("ai", {}).get("voice", True) or not (text or "").strip():
            return
        if not self._speech_open:
            self._speech_open = True
            # Say what is about to be said BEFORE muting: a speaker tail picked up after
            # the mute lifts is then recognised as ours instead of becoming a question.
            try:
                self.wake_server.send("said", text=self._spoken_so_far())
            except Exception:
                pass
            self.wake_server.send("mic", state="off")   # half duplex

            def _done() -> None:
                self._speech_open = False
                self.wake_server.send("mic", state="on")
            self.voice.speak(text, append=True, on_done=_done)
        else:
            self.voice.speak(text, append=True)

    def _spoken_so_far(self) -> str:
        """The answer being spoken, for the daemon's echo guard. Cheap and bounded."""
        try:
            said = getattr(self, "_last_reply_text", "") or ""
        except Exception:
            said = ""
        return said[-400:]

    def _on_speak_end(self) -> None:
        self.voice.close_stream()

    def _on_tool(self, name: str, args: str, result: str) -> None:
        self.console.add_tool(name, args, result)
        self.console.refresh_activity()

    def cancel_current(self) -> bool:
        """Stop means stop: speech first, then the worker, and say which happened."""
        from .. import activity as _activity
        act = _activity.activity()
        stopped = False
        try:
            if self.voice.speaking:
                self.voice.stop()
                stopped = True
        except Exception:
            pass
        if act.busy:
            act.cancel()
            self.console.add_note("STOPPED · you stopped this request")
            stopped = True
        # the wake daemon waits on its own reply; ask it to drop that wait too, but
        # only if this build's runner has the hook (it is an optional extra, not a
        # reason for Stop to raise)
        try:
            if getattr(self.wake_daemon, "thinking", False) and \
                    hasattr(self.wake_daemon, "stop_thinking"):
                self.wake_daemon.stop_thinking()
                stopped = True
        except Exception:
            pass
        self.console.set_busy(False)
        self.companion.set_state(IDLE)
        if not stopped:
            self.console.add_note("nothing was running")
        self.console.refresh_activity()
        return stopped

    def _on_ai_error(self, text: str) -> None:
        self.console.add_note("⚠ " + text)
        self.companion.set_state(IDLE)

    def _on_brain(self, _label: str = "") -> None:
        self.console.set_status(self.agent.describe())

    def _on_confirm(self, name: str, args: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("JARVIS needs permission")
        box.setText(f"JARVIS wants to run:  {name}\n\nArguments: {args}\n\nAllow?")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        granted = box.exec() == QMessageBox.StandardButton.Yes
        self.console.add_note(("allowed" if granted else "denied") + f" · {name}")
        self.agent.answer_confirm(granted)

    # ---------------------------------------------------------------- mic
    def listen_once(self) -> None:
        if self.voice.stt_label() == "unavailable":
            self.console.add_note("⚠ speech input needs Windows. Type instead.")
            return
        self.console.add_note("MIC · listening for ~6 seconds…")
        self.companion.set_state(LISTENING)

        def work() -> None:
            text = self.voice.listen(6)
            self._heard.emit(text)
        threading.Thread(target=work, daemon=True, name="arc-stt").start()

    def _on_heard(self, text: str) -> None:
        self.companion.set_state(IDLE)
        if text:
            self.console.add_note(f"MIC · heard: {text}")
            self.ask(text)
        else:
            self.console.add_note("MIC · nothing recognised")

    def _on_mic_state(self, s: str) -> None:
        self.companion.set_state(s)

    # ------------------------------------------------------------- mcp
    def _boot_mcp(self) -> None:
        """Start the MCP servers off the GUI thread and report through a signal.

        The report used to be `QTimer.singleShot(0, …)` called *from the worker*: a QTimer
        created on a thread with no event loop never fires, so the line it was supposed to
        print simply never appeared — "the app shows nothing while it works".
        """
        from .. import uiwork

        def work(_cancel):
            started = self.mcp.start_all()
            tools.bind_mcp(self.mcp)
            return started, list(self.mcp.errors)

        def done(pair):
            started, errors = pair
            self.console.add_note("MCP · " + ", ".join(started) if started
                                  else "MCP · no servers started")
            for err in errors:
                self.console.add_note("MCP · " + err)

        uiwork.run(work, done=done, name="arc-mcp-boot")

    def restart_mcp(self) -> None:
        """Apply changed MCP server settings without restarting the app."""
        self.mcp.stop_all()
        tools.bind_mcp(None)
        mcfg = self.cfg.setdefault("mcp", {})
        self.mcp = MCPManager()
        if mcfg.get("enabled", True) and mcfg.get("servers"):
            self.mcp.load(mcfg["servers"])
            threading.Thread(target=self._boot_mcp, daemon=True,
                             name="arc-mcp-restart").start()
        else:
            self.console.add_note("MCP · disabled")

    def mcp_summary(self) -> str:
        try:
            return self.mcp.describe()
        except Exception:
            return "MCP unavailable"

    # ---------------------------------------------------------- magic mode
    def enter_magic(self) -> None:
        """Hey JARVIS: fullscreen JARVIS workspace + wallpaper swap (both reversible).

        Order matters, and it was wrong: the old version painted a 2560x1440 wallpaper
        (168 ms measured), asked Windows to swap it, built the screen and only then showed
        anything. On the user's laptop that is the "magic begins open pana slow aaguthu".
        The screen is now shown first — it is the thing being waited for — and the
        wallpaper is prepared and applied afterwards, off the GUI thread.
        """
        mcfg = self.cfg.setdefault("magic", {})
        if self.magic_active:
            return
        if mcfg.get("enabled", True) is False:
            self.toggle_console(True)
            return
        exit_phrase = str(mcfg.get("exit_phrase") or "bye jarvis")

        self._magic_screen = MagicScreen(self.theme, exit_phrase)
        self._magic_screen.exit_requested.connect(self.exit_magic)
        self._magic_screen.command.connect(self._magic_command)
        self._magic_screen.app_requested.connect(self._magic_app)
        self.magic_active = True
        self._cinematic_open()          # hidden when the wake word already said it

        self.hide()
        self.overlay.hide()
        self.palette.hide()
        # the six apps are painted strands now, not buttons - the screen sets its own
        # pointing cursor when the mouse is over one (widgets/magicscreen.py)
        self._magic_screen.show_fullscreen()
        self._magic_screen.set_status("JARVIS · READY")
        if self._tray is not None:
            self.notify("Magic mode on · say \"bye jarvis\" to return")

        # ---- the wallpaper, after the screen is up -----------------------
        if mcfg.get("wallpaper", True):
            self._magic_wallpaper_async()

    def _magic_wallpaper_async(self) -> None:
        """Paint, then apply, the magic wallpaper without holding up the screen.

        Painting is pure CPU and can happen on a worker thread; the Windows call that
        swaps the wallpaper must come back to the GUI thread, so it is queued.
        """
        target = Path(config.data_dir()) / "arc_wallpaper.png"
        theme = self.theme

        def work(_cancel):
            started = time.perf_counter()
            try:
                ok = render_wallpaper(target, theme)
            except Exception:                                    # noqa: BLE001
                ok = False
            return ok, (time.perf_counter() - started) * 1000

        def apply(pair) -> None:
            ok, slow_ms = pair
            if not self.magic_active:
                return                                     # left already: change nothing
            ok2, detail = self.magic.enter(target if ok else None, ok)
            self.console.add_note("MAGIC · " + detail)
            if self.magic.last_error:
                self.console.add_note("MAGIC · " + self.magic.last_error)

        from .. import uiwork
        uiwork.run(work, done=apply, name="magic-wallpaper")

    def exit_magic(self, farewell: bool = True) -> None:
        """BYE JARVIS: everything back exactly as it was.

        `farewell=False` is for leaving the deck in order to do something on Windows itself
        (opening the browser, opening Settings). That path must NOT say goodbye and must
        NOT run `_apply_bye_action` — which can quit the app — just because a strand was
        clicked.
        """
        if not self.magic_active:
            return
        ok, detail = self.magic.exit()
        self.magic_active = False
        if self._magic_screen is not None:
            self._magic_screen.hide()
            self._magic_screen.deleteLater()
            self._magic_screen = None
        if self._holo_window is not None:
            self._holo_window.close()
            self._holo_window.deleteLater()
            self._holo_window = None
        self.console.add_note("MAGIC · " + detail)
        if not farewell:
            return
        # The way out gets the same treatment as the way in: a cue, "Thank you,
        # commander", and only then whatever "close" means in settings. Before this,
        # leaving magic mode was silent and instant — which felt like a crash.
        self.farewell_and_close()

    def _apply_bye_action(self) -> None:
        """What the application itself does once the screen is back to normal.

        Split out of exit_magic() so that "bye jarvis" behaves the SAME whether or not
        magic mode happened to be active. Before this, saying "bye jarvis" with magic
        mode off only printed a note — the app stayed open, which is not what "close"
        means.
        """
        action = str(self.cfg.get("shadow", {}).get("bye_action", "exit"))
        if action == "quit":
            self.close_application(hard=True)
            return
        if action == "exit":
            self.close_application()
            return

        if self.cfg.get("shadow", {}).get("enabled", False):
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
        c = self.cfg.get("charms", {})
        if c.get("enabled", True) and self.theme.effects >= 0.2:
            self.overlay.show()
        if self._tray is not None:
            self.notify("Normal Windows mode")

    def _ears_can_stay(self, have=None) -> tuple[bool, str]:
        """Could a launcher daemon still hear "hey jarvis" after this window closes?

        Checked BEFORE quitting, because quitting on a machine with no microphone
        library would leave the user with a closed app and no way to call it back —
        silently. Better to keep the app in the tray and say why.

        `have` is injectable so the *accept* branch can be tested on a machine with no
        microphone at all. (The first version of this accidentally shadowed the injected
        probe with a real one, so the test could never pass — hence the explicit `probe`.)
        """
        if have is None:
            from ..widgets.voice_ready import can_listen
            return can_listen()

        probe = have
        if not probe("sounddevice"):
            return False, ("sounddevice is not installed, so nothing could hear you "
                           "after the app closes")
        engines = [e for e in ("openwakeword", "vosk") if probe(e)]
        if engines:
            return True, engines[0]
        return False, ("no speech engine (vosk or openwakeword) is installed, so the "
                       "launcher could not hear you")

    def _arm_launcher(self, spawn=None, have=None) -> tuple[object | None, str]:
        """Start the standalone ear and PROVE it is still alive.

        Returns (process, reason_it_failed). `spawn` exists so a test can pass a fake
        process instead of the real one — there is no hidden test environment variable.

        The 1.5 s wait is the whole point: a launcher that dies instantly (no model
        downloaded, port taken, engine missing) is worse than no launcher, because the
        app would already have closed and nothing would be listening.
        """
        from ..paths import daemon_command

        can_hear, why = self._ears_can_stay(have=have)
        if not can_hear:
            return None, why

        try:
            cmd, kwargs = daemon_command(
                int(self.cfg["wake"].get("port", 8765)),
                str(self.cfg["wake"].get("phrase") or "hey jarvis"),
                str(self.cfg["wake"].get("engine") or "auto"),
                str(self.cfg.get("magic", {}).get("exit_phrase") or "bye jarvis"),
                launcher_app="1")
            # quiet.popen, not subprocess.Popen: the launcher is the process the user
            # sees most often, and a console window here is the loudest possible bug.
            # start_new_session now lives in daemon_command's kwargs (translated to
            # DETACHED_PROCESS on Windows), because passing the POSIX name to Windows
            # raises ValueError instead of detaching.
            spawn = spawn or quiet.popen
            proc = spawn(cmd, cwd=str(config.data_dir()), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **kwargs)
        except Exception as exc:
            return None, f"the launcher could not start ({type(exc).__name__}: {exc})"

        # Watch it for 1.5 s — but through a real event loop, not `processEvents()` and
        # `time.sleep()`. The old loop held the drawing thread for a second and a half at
        # the exact moment the window is supposed to be closing, so "quit" looked like a
        # freeze and the window sat there, still on screen, while nothing repainted.
        loop = QEventLoop()
        state = {"died": False}

        def poll() -> None:
            if proc.poll() is not None:
                state["died"] = True
                loop.quit()
            elif time.time() >= deadline:
                loop.quit()

        deadline = time.time() + 1.5
        timer = QTimer(self)
        timer.setInterval(50)
        timer.timeout.connect(poll)
        timer.start()
        QTimer.singleShot(1550, loop.quit)           # a hard stop, whatever happens
        loop.exec()
        timer.stop()
        if state["died"]:
            return None, (f"the launcher exited immediately (code {proc.returncode}); "
                          f"check %APPDATA%\\ArcDesk\\logs for why")
        return proc, ""

    def close_application(self, hard: bool = False, spawn=None) -> None:
        """Close the application for real — that is what "BYE JARVIS" promises.

        hard=False  keep the ears: arm a launcher daemon first, and only quit once it is
                    proven alive. If it cannot stay, do NOT quit into silence — hide and
                    say why.
        hard=True   quit and leave nothing behind (the "quit" choice in Settings, and
                    what Ctrl+Alt+Q does).
        """
        self._save_geometry()
        self.cfg.setdefault("charms", {})["items"] = self.overlay.dump()
        config.save(self.cfg)
        self.overlay.hide()
        self.wake_server.stop()

        keep_ears = (not hard
                     and self.cfg.get("wake", {}).get("enabled", False)
                     and self.cfg.get("shadow", {}).get("relaunch_on_wake", True))

        # The app's own daemon must let go of the microphone BEFORE the launcher takes it.
        self.wake_daemon.stop()

        launcher = None
        if keep_ears:
            launcher, why_not = self._arm_launcher(spawn=spawn)
            if launcher is None:
                if self.cfg.get("shadow", {}).get("enabled", False):
                    self.hide()
                message = (f"BYE JARVIS heard, but I stayed open: {why_not}. "
                           f"Close me with Ctrl+Alt+Q, or install the voice extras "
                           f"(install_voice.bat) so I can be called back by voice.")
                self.console.add_note("VOICE · " + message)
                if self._tray is not None:
                    self.notify(message)
                return
            self.console.add_note(
                f"VOICE · closing the window; launcher armed (pid {launcher.pid}) — "
                f"say \"hey jarvis\" to bring me back")

        self.hotkeys.stop()
        self.mcp.stop_all()
        QGuiApplication.instance().quit()

    def _magic_command(self, text: str) -> None:
        low = text.lower().strip()
        if low in ("exit", "quit", "bye", "normal", "back"):
            self.exit_magic()
            return
        if self._magic_screen is not None:
            self._magic_screen.set_status("WORKING…")
        self.ask(text)

    def _magic_app(self, target: str) -> None:
        """One click on a strand must always do something visible — never a frozen deck.

        What went wrong (`21.png`'s follow-up, "task click pana process aaga matiku,
        appadiyae hang aagi nikkithu"):

        * **TASK MGR** called `psutil.process_iter` on the drawing thread. The click was
          taken, nothing was painted, and the whole screen waited for the process table.
        * **SETTINGS** called `tools.call("open_app", {"app": "settings"})` — a child
          process — from the drawing thread, *and* the dialog it should have opened was
          parented behind a fullscreen always-on-top deck.
        * **BROWSER** launched a window that landed **behind** the deck, so the click looked
          like it did nothing at all.

        Now: the deck's own pages open inside it (unchanged, instant); anything that lives
        on Windows first LEAVES the deck (without the goodbye, which could quit the app),
        then launches on a worker, then says what happened on the deck's status line.
        """
        from .. import uiwork

        def status(text: str) -> None:
            if self._magic_screen is not None:
                self._magic_screen.set_status(text[:60].upper())
            self.console.add_note("MAGIC · " + text)

        # 0. say something BIG, in the middle of the web, before doing anything. A click
        #    that works and a click that is ignored must not look the same.
        label = (target.split(":", 1)[1] if target.startswith("dock:") else target).upper()
        if self._magic_screen is not None:
            self._magic_screen.set_opening(f"opening {label}…")
            self._magic_screen.set_status(f"OPENING {label}")

        # 1. ours, and it opens inside the deck: nothing to wait for.
        if target == "settings":
            status("leaving the deck for settings")
            self.exit_magic(farewell=False)
            QTimer.singleShot(220, self.open_settings)
            return
        if self._magic_screen is not None and self._magic_screen.open_app(target):
            deck = self._magic_screen
            # the panel is up, so the card has done its job — clear it, but not so fast
            # that the person never sees the acknowledgement
            QTimer.singleShot(1200, deck.clear_opening)
            return

        # 2. a Windows program or the web: leave the deck, or the window lands behind it.
        status(f"opening {target} — leaving the deck first, so you can see it")
        self.exit_magic(farewell=False)

        def work(_cancel):
            if target.startswith("http"):
                return tools.call("open_url", {"url": target})
            return tools.call("open_app", {"app": target})

        def done(out):
            self.console.add_note("MAGIC · " + str(out)[:160])
            if not target.startswith("http"):
                # it needs a moment to have a window worth raising
                QTimer.singleShot(900, lambda t=target: self._raise_launched(t))

        def failed(text: str) -> None:
            # The deck has already stepped aside, so a silent failure is a bare desktop
            # and a person who thinks the app froze. Say it, and bring a window back.
            self.console.add_note(f"MAGIC · could not open {target} ({text}) — press "
                                  f"Ctrl+Alt+J or click the tray to come back")
            self.show_now(reason=f"could not open {target}")

        answered = {"yes": False}

        def note_once(text: str) -> None:
            answered["yes"] = True
            self.console.add_note("MAGIC · " + text)

        def slow() -> None:
            if not answered["yes"]:
                note_once(f"{target} has not opened yet — it is still trying, and the rest "
                          f"of JARVIS is usable")

        QTimer.singleShot(6000, slow)
        uiwork.run(work, done=lambda out: (note_once(str(out)[:120]), done(out)),
                   failed=lambda text: (answered.update(yes=True), failed(text)),
                   name="arc-magic-open")

    def _raise_launched(self, target: str) -> None:
        """Bring an app that was launched from the deck to the front, over the deck."""
        try:
            from .. import actions as _actions
            _actions.windows("focus", _APP_TITLES.get(target, target))
        except Exception:                                        # noqa: BLE001
            pass

    def _on_magic_request(self, action: str) -> None:
        if action == "toggle":
            self.toggle_magic()
        elif action == "on":
            self.enter_magic()
        else:
            self.exit_magic()

    def toggle_magic(self) -> None:
        if self.magic_active:
            self.exit_magic()
        else:
            self.enter_magic()

    # ------------------------------------------------------ gravity charms
    def show_charms(self, on: bool) -> None:
        c = self.cfg.setdefault("charms", {})
        c["user_choice"] = True          # a person asked; never migrate this away
        c["enabled"] = bool(on)
        if on and (self.theme.effects < 0.2 or not self.cfg.get("animations", True)):
            self.console.add_note("CHARMS · suppressed by the current mode")
            on = False
        if on:
            self.overlay.set_theme(self.theme)
            self.overlay.show()
        else:
            self.overlay.hide()
            if self.overlay.editing:
                self.overlay.set_edit(False)
        config.save(self.cfg)

    def toggle_charms(self) -> None:
        self.show_charms(not self.overlay.isVisible())

    def edit_charms(self, on: bool | None = None) -> None:
        want = (not self.overlay.editing) if on is None else bool(on)
        if want and not self.overlay.isVisible():
            self.show_charms(True)
        self.overlay.set_edit(want)

    def _on_charms_edit(self, on: bool) -> None:
        self.console.add_note(
            "CHARMS · edit mode ON - drag to move, wheel to resize, right-click for options"
            if on else "CHARMS · edit mode off (click-through again)")
        self.lbl_ready.setText(
            "CHARMS EDIT · DRAG · WHEEL RESIZE · RIGHT-CLICK MENU" if on else HINT_IDLE)

    def _on_charms_changed(self) -> None:
        self.cfg.setdefault("charms", {})["items"] = self.overlay.dump()
        config.save(self.cfg)

    # --------------------------------------------------- windows untouched
    def verify_untouched(self) -> None:
        """Compare the shell against a baseline and scan our own source. Both
        checks run on a worker thread so a slow disk cannot stutter the UI."""
        from .. import desktop_guard

        def work(_cancel) -> str:
            base_path = config.data_dir() / "desktop_baseline.json"
            lines: list[str] = []
            try:
                snap = desktop_guard.snapshot()
                if not base_path.exists():
                    import json
                    base_path.write_text(json.dumps(snap, indent=2), "utf-8")
                    lines.append("baseline saved just now (first check)")
                    diffs = []
                else:
                    import json
                    before = json.loads(base_path.read_text("utf-8"))
                    diffs = desktop_guard.compare(before, snap)
                if diffs:
                    lines.append("shell CHANGED since baseline:")
                    lines.extend("  ! " + d for d in diffs)
                else:
                    lines.append("wallpaper, desktop icons, taskbar, theme: UNCHANGED")
            except Exception as exc:
                lines.append(f"snapshot failed: {type(exc).__name__}: {exc}")

            problems = desktop_guard.scan_sources()
            if problems:
                lines.append(f"code scan: {len(problems)} desktop-altering call(s) found")
                lines.extend("  ! " + p for p in problems[:5])
            else:
                lines.append("code scan: no wallpaper/taskbar/icon APIs anywhere")

            lines.append("Arc Desk only writes inside %APPDATA%\\ArcDesk and timestamped "
                         "screenshots in Pictures.")
            return "\n".join(lines)

        from .. import uiwork
        uiwork.run(work, done=self._show_audit, name="arc-audit")
        self.console.add_note("AUDIT · checking your Windows…")

    def _show_audit(self, text: str) -> None:
        lines = text.splitlines()
        for ln in lines:
            self.console.add_note("AUDIT · " + ln)
        box = QMessageBox(self)
        box.setWindowTitle("Arc Desk · Windows untouched")
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Information)
        box.exec()

    # -------------------------------------------------- shadow / hotkeys
    def _on_hotkey(self, action: str) -> None:
        if action == "palette":
            self.palette.set_theme(self.theme)
            self.palette.popup()
        elif action == "quit":
            self.shutdown()

    def _on_hotkey_failed(self, msg: str) -> None:
        self.console.add_note("HOTKEY · " + msg)
        self.lbl_ready.setText("HOTKEY · " + msg.upper())

    def shutdown(self) -> None:
        """The kill switch. Always reachable: Ctrl+Alt+Q or the menu."""
        self._save_geometry()
        self.cfg["shortcuts"] = self.shelf.dump()
        self.cfg.setdefault("charms", {})["items"] = self.overlay.dump()
        self.overlay.hide()
        if self.magic_active:
            self.magic.exit()
            self.magic_active = False
        config.save(self.cfg)
        self.wake_daemon.stop()
        self.wake_server.stop()
        self.hotkeys.stop()
        self.mcp.stop_all()
        QGuiApplication.instance().quit()

    # ---------------------------------------------------------- awakening
    def awaken(self, message: str = "JARVIS // ONLINE") -> None:
        """Voice said the word: take the screen over, then land in the app."""
        if self._awakening is not None:
            return
        self._cinematic_open()
        self._pre_awaken_shown = self.isVisible()
        self.show()
        self.raise_()
        self.activateWindow()
        if not self.cfg.get("shadow", {}).get("awaken", True) or self.theme.effects < 0.2:
            self._after_awakening()
            return
        self.hide()
        self._awakening = Awakening(self.theme, message)
        self._awakening.finished.connect(self._after_awakening)
        self._awakening.show()

    def _after_awakening(self) -> None:
        self._awakening = None
        target = str(self.cfg.get("shadow", {}).get("awaken_mode", "chill"))
        if target in THEMES and target != self.theme.key:
            self.set_mode(target)
        if self.cfg.get("magic", {}).get("enabled", True):
            self.enter_magic()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self.toggle_console(True)
        self.companion.set_state(LISTENING)
        self.lbl_ready.setText("JARVIS ONLINE · AT YOUR SERVICE")
        if self._tray is not None:
            self.notify("JARVIS online · listening")

    # ------------------------------------------------------ palette glue
    def _palette_reply(self, text: str) -> None:
        self.palette.show_line(text, self.theme.accent)
        self.palette.done()

    def _palette_tool(self, name: str, args: str, result: str) -> None:
        short = result if len(result) <= 120 else result[:120] + "…"
        self.palette.show_line(f"⚙ {name}: {short}", QColor(self.theme.dim).lighter(160).name())

    def _palette_error(self, text: str) -> None:
        self.palette.failed(text)

    # ---------------------------------------------------------- wake word
    def _wake_boot(self) -> None:
        w = self.cfg.get("wake", {})
        if not w.get("enabled"):
            self._set_wake_pill(False)
            return
        self._start_wake()

    def _start_wake(self) -> None:
        w = self.cfg.get("wake", {})
        phrase = str(w.get("phrase") or "hey jarvis")
        if not self.wake_server.listening:
            if not self.wake_server.start():
                self._on_wake_failed("could not open the wake port")
                return
        if w.get("autostart_daemon", True) and not self.wake_daemon.running:
            ok = self.wake_daemon.start(
                int(w.get("port", 8765)), phrase,
                str(w.get("engine") or "auto"),
                str(self.cfg.get("magic", {}).get("exit_phrase", "bye jarvis")),
                launcher_app=None,
                converse=bool(w.get("converse", True)),
                turns=int(w.get("converse_turns", 6)),
                voice_lock=bool(w.get("voice_lock", False)),
                command_seconds=float(w.get("command_seconds", 12)),
                silence_seconds=float(w.get("silence_seconds", 1.8)),
                max_command_seconds=float(w.get("max_command_seconds", 30)))
            if not ok:
                self.console.add_note("VOICE · " + (self.wake_daemon.last_error or
                                                    "daemon did not start"))
        self._set_wake_pill(True)

    def _stop_wake(self) -> None:
        self.wake_daemon.stop()
        self.wake_server.stop()
        self._set_wake_pill(False)
        self.console.set_status(self.agent.describe())

    def _set_wake_pill(self, on: bool) -> None:
        phrase = str(self.cfg.get("wake", {}).get("phrase") or "hey jarvis")
        self.wake_pill.setText(("WAKE · " + phrase.upper()) if on else "WAKE OFF")
        self.wake_pill.setProperty("on", on)
        self.wake_pill.style().unpolish(self.wake_pill)
        self.wake_pill.style().polish(self.wake_pill)

    def toggle_wake(self, force: bool | None = None) -> None:
        w = self.cfg.setdefault("wake", {})
        want = (not w.get("enabled")) if force is None else bool(force)
        w["enabled"] = want
        config.save(self.cfg)
        if want:
            self._start_wake()
            self.console.add_note(f'VOICE · wake word armed: "{w.get("phrase")}"')
        else:
            self._stop_wake()
            self.console.add_note("VOICE · wake word off")

    def _on_request_art(self, sketch) -> None:
        """Show the drawing, and let the window's input line edit it."""
        from .artview import ArtWindow
        if getattr(self, "_art_window", None) is None:
            self._art_window = ArtWindow(self.theme, self)
            self._art_window.on_edit = self._art_edit
        self._art_window.show_sketch(sketch)

    def _on_request_photo(self, path: str, caption: str = "") -> None:
        """A real photograph found by the `photo` tool — same easel, new picture."""
        from .artview import ArtWindow
        if getattr(self, "_art_window", None) is None:
            self._art_window = ArtWindow(self.theme, self)
            self._art_window.on_edit = self._art_edit
        self._art_window.show_photo(path, caption)

    def _art_edit(self, instruction: str) -> str:
        from ..ai import tools as ai_tools
        return ai_tools.call("art_edit", {"instruction": instruction})

    def summon(self) -> None:
        """Someone asked for the window: put a real, visible window on screen.

        This is a second double-click, `jarvis_state --wake`, or the tray menu — not the
        wake word. It used to go through `_on_wake()` → `awaken()`, which **hides** the
        window and shows a fullscreen arrival clip. When that clip cannot draw (a remote
        session, a VM, a driver hiccup, a laptop on an external screen) the result is no
        window at all, while the process sits alive in the tray — which is exactly the
        report: **"jarvis.bat double click pana terminal open aaguthu, jarvis run aaga
        matiku"**. A person who asks for the window gets the window; the cinematic stays
        where it belongs, on the wake word.
        """
        try:
            self.console.set_status("summoned")
        except Exception:
            pass
        self.show_now("a second launch asked for the window")

    def show_now(self, why: str = "asked for the window") -> None:
        """Show the window (or the deck) and take the focus. No animation, no hiding."""
        try:
            if self.magic_active and self._magic_screen is not None:
                self._magic_screen.showFullScreen()
                self._magic_screen.raise_()
                self._magic_screen.activateWindow()
                self.magic_active = True
            else:
                if self.isMinimized():
                    self.showNormal()
                if not self.isVisible():
                    self.show()
                self.raise_()
                self.activateWindow()
        except Exception as exc:                                 # noqa: BLE001
            # A widget that cannot be shown is a bug worth a line, never a crash on a
            # path whose whole purpose is "make the app appear".
            try:
                self.console.add_note(f"WAKE · could not show the window ({exc})")
            except Exception:
                pass
        # The launcher reads this line out of the log to prove a window exists: an
        # accepted socket message is not proof of anything.
        try:
            from .. import logs as _logs
            _logs.note(f"WAKE · the window is in front — {why}")
        except Exception:                                        # noqa: BLE001
            pass

    def _on_wake(self) -> None:
        sfx.play("wake", self.cfg)
        self.console.set_status("listening…")
        if self.magic_active:
            self._magic_screen and self._magic_screen.set_status("ALREADY ACTIVE")
            return
        self.awaken()

    def _on_exit_phrase(self) -> None:
        # "bye jarvis" while the cinematic is still playing should abort it, not
        # be swallowed and let magic mode open a moment later.
        if self._awakening is not None:
            self._awakening.cancel()
            self._awakening = None
            self.console.add_note("MAGIC · awakening cancelled")
            self.lbl_ready.setText(HINT_IDLE)
            if not self.cfg.get("shadow", {}).get("enabled", False):
                self.show()
            return
        if self.magic_active:
            self.exit_magic()
        else:
            self.console.add_note("MAGIC · exit phrase heard (magic mode was not active)")
            # "Thank you, commander" first, then close/hide/quit — per settings.
            self.farewell_and_close()

    def _on_wake_command(self, text: str) -> None:
        self.console.add_note(f'HEARD · "{text}"')
        self.ask(text)

    def _on_wake_status(self, msg: str) -> None:
        self.console.add_note("VOICE · " + msg)
        if msg:
            self.lbl_ready.setText(msg.upper())

    def _on_wake_failed(self, msg: str) -> None:
        self.console.add_note("VOICE · " + msg)
        self._set_wake_pill(False)

    def test_wake(self) -> None:
        """Fire a simulated wake+command so the pipeline can be checked without a mic."""
        w = self.cfg.get("wake", {})
        if not self.wake_server.listening:
            if not self.wake_server.start():
                self.console.add_note("VOICE · could not open the wake port")
                return
        import subprocess
        import sys as _sys
        from pathlib import Path as _Path
        script = _Path(__file__).resolve().parents[2] / "arc_daemon.py"
        try:
            quiet.popen([_sys.executable, str(script), "--port",
                              str(int(w.get("port", 8765))),
                              "--simulate", "system report"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.console.add_note("VOICE · test signal sent")
        except Exception as exc:
            self.console.add_note(f"VOICE · test failed: {exc}")

    # ------------------------------------------------------------- timers
    def add_timer(self, seconds: int, label: str) -> None:
        t = QTimer(self)
        t.setSingleShot(True)

        def fire() -> None:
            self.notify(f"TIMER · {label} finished")
            self.console.add_note(f"TIMER · {label} finished")
            self.voice.speak(f"Your {label} is done.")
            try:
                self._timers.remove(t)
            except ValueError:
                pass
            t.deleteLater()

        t.timeout.connect(fire)
        t.start(max(1, int(seconds)) * 1000)
        self._timers.append(t)
        self.console.add_note(f"TIMER · {label} · {seconds // 60 or 1} min started")

    def notify(self, message: str) -> None:
        if self._tray is not None:
            try:
                self._tray.showMessage("Arc Desk", message,
                                       self._tray.icon(), 6000)
                return
            except Exception:
                pass
        self.console.add_note(message)

    def show_holo(self) -> str:
        """Open the standalone hologram deck (the 'scientific server' view)."""
        from .holo import HoloWindow
        try:
            if self._holo_window is None:
                self._holo_window = HoloWindow(self.theme)
            self._holo_window.set_theme(self.theme)
            self._holo_window.show_deck()
            self.console.add_note("HOLO · deck projected · Esc to close")
            return "hologram deck projected — Esc closes it"
        except Exception as exc:
            return f"could not open the deck: {type(exc).__name__}: {exc}"

    def attach_tray(self, tray) -> None:
        self._tray = tray

    # ------------------------------------------------------------- events
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        """Two jobs, one filter: the reactor's mouse buttons, and Esc from anywhere.

        Esc used to be handled only in `keyPressEvent`, which never fires when the chat
        field, the transcript or the palette hold the focus — the user's words were
        "esc kodutha close aaga matiku". A filter sees the key first, whatever has the
        focus, and hands it to `handle_escape()`.
        """
        # This runs for every event of every child — thousands a second while a dialog
        # lays itself out. The stall log caught the old version: "the window was frozen
        # for 0.5 s — main thread was in window.py:1834 in eventFilter". Cheap questions
        # first, and everything else is handed straight back to Qt.
        #
        # The whole body is shielded because the crash report showed a dead window's
        # events reaching this filter: "No Qt Window found for event 0x46", a minute of
        # it, then a Windows access violation on the next dispatch, this frame on top.
        # `shiboken6.isValid` is the check that makes the dead-object question answerable
        # in Python instead of in the memory manager: a deleted C++ object reads False
        # here, and the answer to any event about it is simply "not me".
        try:
            if not shiboken6.isValid(event):
                return False
            kind = event.type()
            if kind != QEvent.Type.KeyPress and obj is not self.reactor:
                # No C++ base-class filter call here on purpose: the MRO below this
                # class has no filter of its own (the base does nothing and returns
                # False), and skipping that virtual call keeps the hottest path in the
                # app — called thousands of times a second while a dialog lays out —
                # from being the spot a heap fault lands in.
                return False
            if obj is self.reactor and kind == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.cycle_mode()
                    return True
                if event.button() == Qt.MouseButton.RightButton:
                    self._show_quick_menu()
                    return True
            if kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                app = QApplication.instance()
                if app is not None:
                    modal = app.activeModalWidget()
                    if modal is not None and shiboken6.isValid(modal):
                        return False      # a dialog owns this Esc (it saves an answer)
                    focused = app.focusWidget()
                    if focused is not None and shiboken6.isValid(focused):
                        holder = focused.window()
                        if shiboken6.isValid(holder) and isinstance(holder, QDialog) \
                                and holder is not self:
                            return False  # a shown dialog owns this Esc
                if self.handle_escape():
                    return True
            return False
        except Exception:
            return False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_quick_menu()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag = None

    def escape_pressed(self) -> None:
        """Esc, from the shortcut: close the topmost thing, then the window, then quit.

        The user's words were "esc kodutha close aaga matiku". The ladder is now
        explicit, and the last rung exists because "close" can honestly mean "get this
        off my screen for good":

            visible dialog   -> close it (and it saves its own answer)
            speech           -> stop the voice
            running task     -> stop the task
            palette / console/ holo -> close that
            window visible   -> hide it, and say how to get it back
            window hidden    -> quit the app (tray icon included)
        """
        try:
            from PySide6.QtWidgets import QApplication as _QApp
            modal = _QApp.activeModalWidget()
            if modal is not None and modal is not self:
                modal.reject()
                return
        except Exception:
            pass
        if self.isVisible():
            self.handle_escape()
            return
        # already hidden: Esc means "then close it properly"
        self.console.add_note("Esc on a hidden window quits Arc Desk")
        try:
            QApplication.instance().quit()
        except Exception:
            self.close()

    def handle_escape(self) -> bool:
        """One place that decides what Esc means. Returns True if it did something."""
        from .. import activity as _activity
        try:
            if self.voice.speaking:
                self.voice.stop()
                self.console.add_note("speech stopped")
                return True
        except Exception:
            pass
        if _activity.activity().busy:
            self.cancel_current()
            return True
        if self.palette.isVisible():
            self.palette.hide()
            return True
        if self._console_open:
            self.toggle_console(False)
            return True
        try:
            if getattr(self, "_holo_window", None) is not None \
                    and self._holo_window.isVisible():
                self._holo_window.close()
                return True
        except Exception:
            pass
        if getattr(self, "_magic_screen", None) is not None \
                and self._magic_screen.isVisible():
            self._magic_screen.close()
            return True
        self.hide()
        self.console.add_note("window hidden — Ctrl+Alt+J or \"hey jarvis\" brings it back")
        return True

    def toggle_maximized(self) -> None:
        """One button for "expand" and "back to a window".

        The window is frameless, so Windows gave it no maximise button at all — the only
        way to enlarge it was to drag (and it could not be dragged). This is the button
        the report asked for: "enakku minimize pana, expand pana".
        """
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setToolTip("Expand to fill the screen")
        else:
            self.showMaximized()
            self.btn_max.setToolTip("Back to a window")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        k = event.key()
        mod = event.modifiers()
        if k == Qt.Key.Key_Escape:
            if not self.handle_escape():     # same decision as the app-wide filter
                super().keyPressEvent(event)
        elif k == Qt.Key.Key_J and mod & Qt.KeyboardModifier.ControlModifier:
            self.toggle_console()
        elif k == Qt.Key.Key_Space and mod & Qt.KeyboardModifier.ControlModifier:
            self.toggle_console(True)
            self.console.focus_input()
        elif k == Qt.Key.Key_P and mod & Qt.KeyboardModifier.ControlModifier and \
                mod & Qt.KeyboardModifier.AltModifier:
            self.palette.popup()
        elif k == Qt.Key.Key_M and not mod:
            self.cycle_mode()
        elif k == Qt.Key.Key_Q and mod & Qt.KeyboardModifier.ControlModifier:
            QGuiApplication.instance().quit()
        else:
            super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        from ..ticker import ticker as _ticker
        _ticker().set_paused(False)
        self.console.refresh_activity()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        """Hidden means hidden: no 30 fps repaint of a window nobody can see.

        Stealth is the resting state, so this is the common case, and it was costing a
        full animation tick 24 hours a day on a laptop.
        """
        from ..ticker import ticker as _ticker
        _ticker().set_paused(True)
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        side = int(max(240, min(self.height() * 0.54, self.width() * 0.42, 450)))
        self.reactor.setFixedSize(side, side)
        super().resizeEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_geometry()
        self.cfg["shortcuts"] = self.shelf.dump()
        config.save(self.cfg)
        if self.cfg.get("minimise_to_tray_on_close", True) and self._tray is not None:
            event.ignore()
            self.hide()
            # A window that disappears with no word reads as a crash ("auto close
            # aaguthu... application failure ah?"). Say, once per session, in the log
            # AND in a tray notice, what actually happened: nothing died.
            if not getattr(self, "_tray_told", False):
                self._tray_told = True
                try:
                    from .. import logs
                    logs.note("UI · the window was closed - JARVIS is not closed, it is "
                              "running in the tray. Ctrl+Alt+J reopens it; Ctrl+Alt+Q "
                              "quits for good")
                except Exception:                                    # noqa: BLE001
                    pass
                try:
                    self.notify("JARVIS is not closed - it is running in the tray. "
                                "Ctrl+Alt+J opens it; Ctrl+Alt+Q quits for good.")
                except Exception:                                    # noqa: BLE001
                    pass
            return
        self.wake_daemon.stop()
        self.wake_server.stop()
        self.hotkeys.stop()
        self.mcp.stop_all()
        if self.magic_active:
            self.magic.exit()
        event.accept()

    # -------------------------------------------------------------- misc
    def _quick_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction("Ask JARVIS  (Ctrl+J)").triggered.connect(lambda: self.toggle_console(True))
        m.addAction("Hologram deck").triggered.connect(self.show_holo)
        m.addAction("Settings…").triggered.connect(self.open_settings)
        m.addAction("Assistant brain…").triggered.connect(self.open_ai_setup)
        m.addSeparator()
        wake = m.addAction("Wake word")
        wake.setCheckable(True)
        wake.setChecked(bool(self.cfg.get("wake", {}).get("enabled")))
        wake.triggered.connect(lambda checked: self.toggle_wake(checked))
        m.addAction("Test wake word (no mic)").triggered.connect(self.test_wake)
        m.addSeparator()
        for key in ("focus", "chill", "gaming", "night"):
            th = THEMES[key]
            act = m.addAction(f"{th.label} mode  ·  {th.hint}")
            act.setCheckable(True)
            act.setChecked(key == self.theme.key)
            act.triggered.connect(lambda _=False, k=key: self.set_mode(k))
        m.addSeparator()
        a = m.addAction("Pause animations")
        a.setCheckable(True)
        a.setChecked(not self.cfg.get("animations", True))
        a.triggered.connect(lambda checked: self.set_animations(not checked))
        w = self.cfg["weather"]
        wact = m.addAction("Weather (needs internet)")
        wact.setCheckable(True)
        wact.setChecked(bool(w.get("enabled")))
        wact.triggered.connect(self._toggle_weather)
        from .. import autostart
        boot = m.addAction("Start with Windows" if os.name == "nt" else "Start at login")
        boot.setCheckable(True)
        boot.setChecked(autostart.is_enabled())
        boot.triggered.connect(self._toggle_autostart)
        m.addSeparator()
        m.addAction("Back up my files to a disk…").triggered.connect(self.backup_now)
        m.addAction("Why is this PC slow?").triggered.connect(self.explain_slowness)
        m.addAction("Index my documents now").triggered.connect(self.index_documents)
        m.addAction("What can I ask?  (all of it)").triggered.connect(
            self.open_tool_reference)
        m.addSeparator()
        m.addAction("Reset window position").triggered.connect(self._reset_pos)
        m.addAction("Awaken (test transformation)").triggered.connect(self.awaken)
        mg = m.addAction("Magic mode  (fullscreen JARVIS + wallpaper)")
        mg.setCheckable(True)
        mg.setChecked(self.magic_active)
        mg.triggered.connect(lambda _c: self.toggle_magic())
        m.addAction("Check: is my Windows untouched?").triggered.connect(
            self.verify_untouched)
        m.addSeparator()
        c = m.addAction("Gravity charms")
        c.setCheckable(True)
        c.setChecked(self.overlay.isVisible())
        c.triggered.connect(lambda checked: self.show_charms(checked))
        m.addAction("Move / resize charms  (edit mode)").triggered.connect(
            lambda: self.edit_charms())
        m.addAction("Add a charm").triggered.connect(lambda: self.overlay.add_charm("bot"))
        m.addAction("Command palette  (Ctrl+Alt+J)").triggered.connect(
            lambda: self.palette.popup())
        m.addAction("Quit Arc Desk  (Ctrl+Alt+Q)").triggered.connect(self.shutdown)
        return m

    def _show_quick_menu(self) -> None:
        self._quick_menu().exec(self.cursor().pos())

    def _toggle_weather(self) -> None:
        w = self.cfg["weather"]
        w["enabled"] = not w.get("enabled")
        config.save(self.cfg)
        if w["enabled"]:
            self.clock.set_weather("FETCHING…", False)
            self.weather._last_fetch = 0.0
            self.weather.refresh(w["lat"], w["lon"], w.get("city", ""),
                                 int(w.get("refresh_min", 20)))
        else:
            self.clock.set_weather("WEATHER · OFFLINE", False)

    def _toggle_autostart(self) -> None:
        from .. import autostart
        want = not autostart.is_enabled()
        ok = autostart.set_enabled(want)
        state = autostart.status()
        self.cfg["autostart"] = autostart.is_enabled()
        config.save(self.cfg)
        if not ok:
            self.console.add_note("Autostart did not change: " + state.get("detail", "?"))
        else:
            self.console.add_note(autostart.report(state))

    def open_tool_reference(self) -> None:
        """Open the generated, searchable list of every tool in the browser.

        It ships inside the app (arcdesk/TOOLS_PAGE.html), so it works offline. If the
        file was somehow not built, say so instead of failing silently.
        """
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from .. import paths
        found = paths.page("TOOLS_PAGE.html")
        if found is None:
            self.console.add_note("The tool reference page is not built — run "
                                  "python tools/gen_tools_doc.py")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(found)))
        self.console.add_note(f"Tool reference opened in your browser — "
                              f"{len(tools.TOOLS)} tools, each with its arguments.")

    # ------------------------------------------------- back up / diagnose
    def _in_background(self, work, label: str) -> None:
        """Run a slow, honest job off the GUI thread and print its answer in the console."""
        from .. import uiwork
        self.console.add_note(label + " …")
        uiwork.run(lambda _cancel: work(),
                   done=lambda text: self.console.add_note(text),
                   failed=lambda text: self.console.add_note(f"{label} failed: {text}"),
                   name="arc-bg")

    def backup_now(self) -> None:
        """Copy the obvious folders to the first external disk, verified — or say why not."""
        from .. import backup

        def work() -> str:
            target = backup.default_target()
            if not target:
                return ("No second drive is attached, so there is nothing safe to copy to. "
                        "Plug in the external disk and try again — I will not back up onto "
                        "the same disk.")
            home = Path(os.environ.get("ARCDESK_USER_HOME") or Path.home())
            sources = [p for p in (home / "Documents", home / "Desktop", home / "Pictures")
                       if p.is_dir()]
            if not sources:
                return "I could not find Documents, Desktop or Pictures to copy."
            lines = []
            for folder in sources:
                result = backup.copy(str(folder), target)
                lines.append(backup.report(result))
            return "\n\n".join(lines)

        self._in_background(work, "Backing up your files (copy + SHA-256 verify)")

    def explain_slowness(self) -> None:
        from .. import pchealth
        self._in_background(lambda: pchealth.explain(), "Measuring this machine for 1 s")

    def index_documents(self) -> None:
        from .. import docs_worker
        if docs_worker.start(self):
            self.console.add_note("Reading your documents in the background — search will "
                                  "work as soon as it finishes.")
        else:
            self.console.add_note("Document indexing is already running.")

    def _reset_pos(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self._save_geometry()
        config.save(self.cfg)

    def _restore_geometry(self) -> None:
        w = self.cfg.get("window", {})
        self.resize(int(w.get("w") or 1000), int(w.get("h") or 668))
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x, y = w.get("x"), w.get("y")
        if x is None or y is None:
            self.move(screen.center() - self.rect().center())
        else:
            self.move(int(x), int(y))
            if not screen.adjusted(-40, -40, 40, 40).contains(self.frameGeometry()):
                self.move(screen.center() - self.rect().center())

    def _save_geometry(self) -> None:
        g = self.geometry()
        self.cfg["window"] = {"w": g.width(), "h": g.height(), "x": g.x(), "y": g.y()}

    def advance(self, seconds: float) -> None:
        """Fast-forward animations (used by --screenshot)."""
        self.reactor.advance(seconds)
        self.companion.advance(seconds)
        self.clock.update()

    # --------------------------------------------------------- background
    def paintEvent(self, event) -> None:  # noqa: N802
        th = self.theme
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        path = QPainterPath()
        path.addRoundedRect(rect, 22, 22)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(th.panel))
        grad.setColorAt(1.0, QColor(th.bg))
        q.fillPath(path, grad)

        q.setPen(QPen(QColor(th.accent).darker(115), 1.4))
        q.setOpacity(0.55)
        q.drawPath(path)
        q.setOpacity(1.0)
        q.end()
