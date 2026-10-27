"""The one page a new user sees before anything else.

Why a dialog and not a docs page: at this point the user has a running app, no
model configured, a microphone they have never tested, and a wake word that is
deliberately off. Three decisions get made here, with the *evidence* next to each
one instead of in a README:

  1. can you hear me?  → speak a line now, so a broken voice is discovered here
                          and not during a demo;
  2. should I listen?  → wake word on/off, with the RAM cost written on the button;
  3. what thinks?      → whichever local engine was detected, or Lite (free,
                          offline, no download), and never a paid one;
  4. should I start with you? → one per-user entry, no admin, removable here or in
                          Task Manager, and off unless ticked;
  5. may I read your documents? → the words inside Word/Excel/PDF, so search works —
                          read-only, opt-in, and it says so.

Steps 4 and 5 are performed by `arcdesk/firstrun.py`, not by this dialog, so the same
rules hold when the user changes their mind by voice ("start with windows") instead of
by clicking.

Nothing here installs anything, starts a service, or writes outside Arc Desk's own
settings folder. Closing the card with Esc is the same as "just use Lite".
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

ACCENT = "#7fe3f0"
DIM = "#8fa3ad"


class WelcomeDialog(QDialog):
    """`Done` writes three settings and nothing else."""

    def __init__(self, cfg: dict, voice=None, engines: list[str] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.voice = voice
        self.setWindowTitle("Arc Desk · first run")
        self.setMinimumWidth(560)
        self.setStyleSheet(
            "QDialog{background:#0a1116;}"
            f"QLabel{{color:#dbe7ec;font-family:Segoe UI;}}"
            f"QLabel#kicker{{color:{ACCENT};font-size:11px;letter-spacing:2px;}}"
            f"QLabel#h1{{font-size:22px;font-weight:600;}}"
            f"QLabel#dim{{color:{DIM};font-size:12px;}}"
            f"QLabel#step{{color:{ACCENT};font-size:11px;letter-spacing:1px;}}"
            "QFrame#card{background:#101a20;border:1px solid #1d2c34;border-radius:10px;}"
            "QPushButton{background:#12242c;color:#dbe7ec;border:1px solid #24404b;"
            "border-radius:6px;padding:6px 12px;}"
            f"QPushButton:hover{{border-color:{ACCENT};}}"
            f"QPushButton#go{{background:{ACCENT};color:#06131a;font-weight:600;}}"
            "QCheckBox{color:#dbe7ec;}"
        )

        # The card list is LONGER than a 768-pixel laptop screen, and it used to be a
        # plain vertical layout — so "Done" and "Just use Lite" were laid out below the
        # bottom of the screen and could not be clicked at all. That is exactly what the
        # user reported: the setup card appeared, nothing else ever opened, and the card
        # came back on the next double-click because setup was never saved. The cards now
        # scroll; the footer does not.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(26, 22, 26, 8)
        lay.setSpacing(12)

        kick = QLabel("JARVIS DESK · SETUP")
        kick.setObjectName("kicker")
        lay.addWidget(kick)
        title = QLabel("Three things, then I am yours.")
        title.setObjectName("h1")
        lay.addWidget(title)
        sub = QLabel("No account, no key, no download required. Everything below "
                     "works offline.")
        sub.setObjectName("dim")
        lay.addWidget(sub)

        # ---- 1. voice ------------------------------------------------
        lay.addWidget(self._card(
            "1 · CAN YOU HEAR ME?",
            "Plays one line through the same engine JARVIS uses for answers. If this is "
            "silent, Settings → Voice is where to fix it.",
            [("Say something", self._test_voice)],
        ))

        # ---- 2. HOW DO YOU WANT TO OPEN ME? -------------------------
        # The user's own words: "first time set pannum pothu voice la open pananuma
        # illa desktop icon double click panra mathiri venuma nu kekanum". So this is
        # one question with two answers, not two checkboxes to interpret.
        from PySide6.QtWidgets import QRadioButton
        self.mode_icon = QRadioButton("Desktop icon — I double-click when I need you")
        self.mode_voice = QRadioButton('Voice — always waiting for "hey jarvis" '
                                       '(starts with Windows, microphone open)')
        self.mode_voice.setChecked(bool(cfg.get("wake", {}).get("enabled")))
        self.mode_icon.setChecked(not self.mode_voice.isChecked())
        self.mode_icon.toggled.connect(self._mode_changed)
        self.mode_voice.toggled.connect(self._mode_changed)

        # kept as the single source of truth so the rest of the app (and the tests)
        # ask one object whether the microphone is armed
        self.wake_box = QCheckBox("Listen for the wake word (adds a ~60–150 MB daemon)")
        self.wake_hint = QLabel("")
        self.wake_hint.setObjectName("dim")
        self.wake_hint.setVisible(False)
        # The expectation is "it is always there, waiting for 'hey jarvis'", so the box
        # starts TICKED — but only when this machine can really hear (mic library + speech
        # engine + model). Ticking a box that cannot work would break the very first
        # "hey jarvis", so instead it says what is missing.
        from ..widgets.voice_ready import can_listen
        can_hear, why = can_listen()
        already = bool(cfg.get("wake", {}).get("enabled"))
        self.wake_box.setChecked(can_hear or already)
        if not can_hear:
            self.wake_box.setToolTip(why)
            self.wake_hint.setText(why + " — tick it anyway and I will tell you exactly "
                                         "what is missing instead of pretending to listen.")
            self.wake_hint.setVisible(True)
        self.ears_btn = QPushButton("Get the ears ready (70 MB)…")
        self.ears_btn.setToolTip("Downloads the 40 MB speech model and the 30 MB speaker "
                                 "model, and says exactly what is still missing if "
                                 "anything is.")
        self.ears_btn.clicked.connect(self.open_ears)
        self.ears_btn.setVisible(not can_hear)
        self.wake_box.toggled.connect(self._wake_hint)
        self.wake_box.setVisible(False)          # driven by the two options above
        self.wake_box.setChecked(self.mode_voice.isChecked())
        lay.addWidget(self._card(
            "2 · HOW DO YOU WANT TO OPEN ME?",
            "Either way every feature works. Typed commands, the tray and Ctrl+Alt+J "
            "are always there; the difference is only whether JARVIS is already running "
            "and listening.",
            widgets=[self.mode_icon, self.mode_voice, self.wake_hint, self.ears_btn],
        ))

        # ---- 3. brain -------------------------------------------------
        found = engines or []
        brain_text = ("Found: " + ", ".join(found) + ". I will use it when it is running.")
        if not found:
            brain_text = ("No local model detected — that is fine. JARVIS Lite answers "
                          "offline in about a millisecond, and you can add Ollama or "
                          "llama.cpp later in Settings → Brain.")
        self.brain_text = brain_text
        self.brain_btn = QPushButton("Add a brain…")
        self.brain_btn.setToolTip("A small local model, downloaded and started from inside "
                                  "the app — no account, no Ollama homework.")
        self.brain_btn.clicked.connect(self.open_brain)
        self._brain_card = self._card("3 · WHAT THINKS?", brain_text,
                                      [("Re-scan", self._rescan), ("Add a brain…",
                                                                   self.open_brain)])
        lay.addWidget(self._brain_card)

        # ---- 4. start with your account -------------------------------
        from arcdesk import autostart as _autostart
        try:
            boot_on = _autostart.is_enabled()
        except Exception:
            boot_on = False
        self.boot_box = QCheckBox("Start Arc Desk when I sign in, silently, so \"hey jarvis\" "
                                  "always works  (no admin, one entry, removable in Task Manager)")
        # Default ON: the whole point of a wake word is that the thing is already running.
        # Still one per-user HKCU value, still removable in two places, still no admin.
        self.boot_box.setChecked(bool(boot_on) or self.mode_voice.isChecked())
        self.boot_box.toggled.connect(self._boot_changed)
        self.boot_hint = QLabel("")
        self.boot_hint.setObjectName("dim")
        self.boot_hint.setWordWrap(True)
        self.boot_hint.setVisible(False)
        lay.addWidget(self._card(
            "4 · START WITH YOU?",
            "Ticked for the voice option, because \"hey jarvis\" can only answer if JARVIS "
            "is already running. One per-user entry, no admin, removable here or in "
            "Task Manager.",
            widgets=[self.boot_box, self.boot_hint],
        ))

        # ---- 5. read documents ---------------------------------------
        self.docs_box = QCheckBox("Read my documents once, so 'which file mentions X' "
                                  "works  (read-only)")
        self.docs_box.setChecked(bool(cfg.get("docs", {}).get("index_on_start", False)))
        lay.addWidget(self._card(
            "5 · MAY I READ?",
            "Word, Excel, PowerPoint, PDF and text from Documents, Desktop and Downloads. "
            "It is read-only: no file is changed, renamed or uploaded, and you can forget "
            "the index in one command.",
            widgets=[self.docs_box],
        ))

        lay.addStretch(1)

        # ---- scrollable cards -----------------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # ---- footer: always on screen, whatever the laptop --------------
        footer = QWidget()
        row = QHBoxLayout(footer)
        row.setContentsMargins(26, 8, 26, 16)
        self.status = QLabel("")
        self.status.setObjectName("dim")
        row.addWidget(self.status, 1)
        self.skip_btn = QPushButton("Just use Lite")
        self.skip_btn.setToolTip("Save nothing except “setup is done” — JARVIS still works "
                                 "offline; every feature stays available.")
        self.skip_btn.clicked.connect(lambda: self._finish(False))
        row.addWidget(self.skip_btn)
        self.go_btn = QPushButton("Start JARVIS")
        self.go_btn.setObjectName("go")
        self.go_btn.setDefault(True)          # Enter finishes, like every other dialog
        self.go_btn.clicked.connect(lambda: self._finish(True))
        row.addWidget(self.go_btn)
        outer.addWidget(footer)

        self._fit_to_screen()
        self.go_btn.setFocus()

    def _fit_to_screen(self) -> None:
        """Never be taller than the screen: 5 cards do not fit on a 768-pixel laptop."""
        need_h = self.sizeHint().height() + 60
        try:
            screen = QGuiApplication.primaryScreen()
            avail = screen.availableGeometry() if screen else None
        except Exception:
            avail = None
        if avail is None:
            self.resize(640, min(need_h, 720))
            return
        h = min(need_h, int(avail.height() * 0.90))
        w = max(600, min(760, int(avail.width() * 0.60)))
        self.resize(w, h)
        self.move(avail.center().x() - w // 2, max(avail.top() + 12,
                                                   avail.center().y() - h // 2))

    # ------------------------------------------------------------------ ui
    def _card(self, step: str, body: str, buttons=None, widgets=None) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        box = QVBoxLayout(frame)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(6)
        head = QLabel(step)
        head.setObjectName("step")
        box.addWidget(head)
        text = QLabel(body)
        text.setWordWrap(True)
        text.setObjectName("dim")
        box.addWidget(text)
        for widget in widgets or []:
            box.addWidget(widget)
        if buttons:
            row = QHBoxLayout()
            for label, slot in buttons:
                btn = QPushButton(label)
                btn.clicked.connect(slot)
                row.addWidget(btn)
            row.addStretch(1)
            box.addLayout(row)
        return frame

    # --------------------------------------------------------------- actions
    def _test_voice(self) -> None:
        from .. import identity
        line = ("All systems are green. Vanakkam macha — " +
                identity.intro(self.cfg))
        if self.voice is None:
            self.status.setText("voice engine unavailable in this window")
            return
        try:
            self.voice.speak(line)
            self.status.setText("said: " + line[:46] + "…")
        except Exception as exc:
            self.status.setText(f"voice failed: {exc}")

    def open_brain(self) -> None:
        """The honest fix for "no local model detected" — inside setup, not homework."""
        from .brain_dialog import BrainDialog
        BrainDialog(self.cfg, self.theme_of_dialog(), parent=self).exec()
        self._rescan()

    def open_ears(self) -> None:
        """The honest fix for a silent wake word — from inside setup, not a command line."""
        from .ears_dialog import EarsDialog
        EarsDialog(self.theme_of_dialog(), parent=self).exec()
        from ..widgets.voice_ready import can_listen
        can_hear, why = can_listen()
        self.wake_box.setEnabled(True)
        self.ears_btn.setVisible(not can_hear)
        if can_hear:
            self.wake_hint.setText("Ears ready — " + why + ". Tick the voice option above "
                                   "to use them.")
        else:
            self.wake_hint.setText(why)
        self.wake_hint.setVisible(True)

    def theme_of_dialog(self) -> dict:
        return getattr(self, "_theme", {}) or {}

    def _mode_changed(self, _checked: bool = False) -> None:
        """One choice moves both flags: the microphone and the startup entry."""
        voice = self.mode_voice.isChecked()
        self.wake_box.setChecked(voice)
        self.boot_box.setChecked(voice or self.boot_box.isChecked())
        if voice:
            self.wake_hint.setText("Microphone stays open. Say 'hey jarvis'. "
                                   "Ctrl+Alt+Q quits at any time.")
            self.wake_hint.setVisible(True)
        else:
            self.wake_hint.setText("Nothing listens and nothing starts by itself — "
                                   "double-click the shortcut when you need me.")
            self.wake_hint.setVisible(True)

    def _boot_changed(self, on: bool) -> None:
        if on and self.mode_icon.isChecked():
            self.boot_hint.setText("Starts silently with Windows, but still waits for a "
                                   "double-click or \"hey jarvis\" once the wake word is on.")
        else:
            self.boot_hint.setText("")
        self.boot_hint.setVisible(bool(on) and self.mode_icon.isChecked())

    def _wake_hint(self, on: bool) -> None:
        self.wake_hint.setText("Microphone stays open. Say 'hey jarvis'. "
                               "Ctrl+Alt+Q quits at any time." if on else "")
        self.wake_hint.setVisible(bool(on))

    def _rescan(self) -> None:
        """Ask which local engines are up — on a worker.

        `backends.probe()` opens a socket per backend (about ten of them) with a 0.25 s
        timeout each, so on the drawing thread this card could freeze for two seconds
        while it said "checking". Nothing here is worth a frozen window.
        """
        from .. import uiwork
        self.status.setText("local engines: checking…")

        def work(_cancel):
            from arcdesk.ai import backends
            return [d.describe() for d in backends.probe()]

        def apply(found):
            self.status.setText("local engines: "
                                + (", ".join(found) if found else "none running"))

        def failed(text: str) -> None:
            self.status.setText(f"local engines: could not check ({text})")

        uiwork.run(work, done=apply, failed=failed, name="arc-backend-scan")

    def closeEvent(self, event) -> None:  # noqa: N802
        """Closing the window is an answer, not a crash.

        The user closed this card with the ✕, setup was never applied, `first_run`
        stayed True, and the same card came back on the next double-click. Whatever is
        on screen is now the answer ("the icon, and nothing else"), so save that.
        """
        if not getattr(self, "setup_result", None):
            self._finish(False)
        super().closeEvent(event)

    def _finish(self, keep_wake: bool) -> None:
        """One place decides what setup means: `firstrun.apply()`.

        Esc / "Just use Lite" passes keep_wake=False, and that is the only thing it
        overrides — the checkbox is still needed to arm a microphone.
        """
        if getattr(self, "_finishing", False):
            return
        self._finishing = True
        from arcdesk import firstrun
        wake = bool(self.wake_box.isChecked() and keep_wake)
        # the checkbox is the truth about the microphone; the radio is how a person
        # expressed it. Read the flag, not the widget, so both paths agree.
        answers = {
            "open_mode": "voice" if wake else "icon",
            "wake": wake,
            "autostart": bool(getattr(self, "boot_box", None)
                              and self.boot_box.isChecked()),
            "documents": bool(getattr(self, "docs_box", None)
                              and self.docs_box.isChecked()),
            "voice": bool(self.cfg.get("ai", {}).get("voice", True)),
        }
        result = firstrun.apply(self.cfg, answers)
        self.setup_result = result                 # the window prints this in the console
        self.accept()

    # Esc is "just use Lite" — the least surprising default
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._finish(False)
            return
        super().keyPressEvent(event)
