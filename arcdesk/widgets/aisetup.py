"""Assistant setup dialog — pick a brain without editing JSON by hand.

Auto-detect order: your key (if given) → Groq → Gemini → OpenAI → local Ollama
→ Lite. "Auto" is the default, so the app just works out of the box and gets
smarter the moment you add a key or install Ollama.
"""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout,
)

from ..ai.llm import PROVIDERS, LLMClient, ollama_alive, ollama_alive_soon
from ..theme import Theme

ORDER = [("auto", "Auto-detect (recommended)")] + [
    (k, v["label"]) for k, v in PROVIDERS.items()
] + [("lite", "JARVIS Lite only (offline, no key, no RAM)")]


class AISetupDialog(QDialog):
    changed = Signal()

    def __init__(self, cfg: dict, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.theme = theme
        self.setWindowTitle("JARVIS — assistant setup")
        self.setMinimumWidth(470)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        head = QLabel("ASSISTANT BRAIN")
        f = head.font()
        f.setPixelSize(10)
        f.setWeight(f.Weight.Bold)
        f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 2.4)
        head.setFont(f)
        lay.addWidget(head)

        note = QLabel(
            "The model never runs inside Arc Desk — that is what keeps the app at ~80 MB. "
            "Groq and Gemini have free tiers; Ollama runs offline on your own machine in its "
            "own process. Leave this on Auto: JARVIS Lite works with nothing installed.")
        note.setWordWrap(True)
        note.setObjectName("setupNote")
        lay.addWidget(note)

        form = QFormLayout()
        form.setSpacing(9)

        self.provider = QComboBox()
        for key, label in ORDER:
            self.provider.addItem(label, key)
        self.provider.currentIndexChanged.connect(self._sync_fields)
        form.addRow("Brain", self.provider)

        self.model = QLineEdit()
        self.model.setPlaceholderText("leave blank for the provider default")
        form.addRow("Model", self.model)

        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("paste an API key, or set GROQ_API_KEY / GEMINI_API_KEY")
        form.addRow("API key", self.key)

        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("only for custom / Ollama endpoints")
        form.addRow("Base URL", self.base_url)
        lay.addLayout(form)

        self.voice = QCheckBox("Speak replies aloud (uses Windows SAPI, no extra RAM)")
        self.voice.setChecked(bool(cfg.get("ai", {}).get("voice", True)))
        lay.addWidget(self.voice)

        self.listen_hint = QLabel("")
        self.listen_hint.setObjectName("setupNote")
        self.listen_hint.setWordWrap(True)
        lay.addWidget(self.listen_hint)

        self.result = QLabel("")
        self.result.setObjectName("setupNote")
        self.result.setWordWrap(True)
        lay.addWidget(self.result)

        row = QHBoxLayout()
        self.btn_test = QPushButton("TEST CONNECTION")
        self.btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test.clicked.connect(self._test)
        row.addWidget(self.btn_test)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(save)
        lay.addLayout(row)

        self._load()
        self._apply_style()

    # -- config ----------------------------------------------------------
    def _load(self) -> None:
        ai = self.cfg.get("ai", {})
        key = ai.get("provider", "auto")
        idx = max(0, self.provider.findData(key))
        self.provider.setCurrentIndex(idx)
        self.model.setText(ai.get("model", "") or "")
        stored = ai.get("api_key", "") or ""
        env_used = self._env_key_for(key)
        self.key.setText(stored)
        if not stored and env_used:
            self.key.setPlaceholderText(f"using {env_used} from the environment")
        self.base_url.setText(ai.get("base_url", "") or "")
        self._ollama: bool | None = None          # unknown until the worker answers
        self._sync_fields()
        # A socket, a request and a 0.6 s timeout, on the drawing thread — that is a
        # frozen window on a slow machine (20.png again). Ask on a worker instead.
        from .. import uiwork
        uiwork.run(lambda _cancel: ollama_alive(), done=self._ollama_answer,
                   name="arc-ollama-probe")

    def _ollama_answer(self, up: bool) -> None:
        self._ollama = bool(up)
        self._sync_fields()

    @staticmethod
    def _env_key_for(provider: str) -> str:
        spec = PROVIDERS.get(provider)
        if spec and spec.get("env") and os.getenv(spec["env"]):
            return spec["env"]
        return ""

    def _sync_fields(self) -> None:
        key = self.provider.currentData()
        spec = PROVIDERS.get(key, {})
        needs = spec.get("needs_key", key not in ("auto", "lite", "ollama"))
        self.key.setEnabled(key not in ("auto", "lite", "ollama"))
        self.base_url.setEnabled(key in ("custom", "ollama", "auto"))
        self.model.setEnabled(key != "lite")
        hint = spec.get("note", "")
        if key == "auto":
            if getattr(self, "_ollama", None) is None:
                seen = "checking…"
            else:
                seen = "yes" if self._ollama else "no"
            hint = ("Auto: uses a key if present, otherwise local Ollama, otherwise JARVIS "
                    f"Lite. Ollama detected: {seen}")
        self.result.setText(hint if not needs or self.key.text() else hint)

    def _save(self) -> None:
        ai = self.cfg.setdefault("ai", {})
        ai["enabled"] = True
        ai["provider"] = self.provider.currentData()
        ai["model"] = self.model.text().strip()
        ai["api_key"] = self.key.text().strip()
        ai["base_url"] = self.base_url.text().strip()
        ai["voice"] = self.voice.isChecked()
        self.changed.emit()
        self.accept()

    # -- connectivity test ------------------------------------------------
    def _test(self) -> None:
        key = self.provider.currentData()
        if key == "lite":
            self.result.setText("JARVIS Lite needs no connection. It is already working.")
            return
        self.btn_test.setEnabled(False)
        self.result.setText("testing…")

        model = self.model.text().strip()
        base = self.base_url.text().strip()
        api_key = self.key.text().strip()

        def work(_cancel) -> str:
            if key == "auto":
                no_key = not any(os.getenv(PROVIDERS[p]["env"] or "")
                                 for p in ("groq", "gemini", "openai"))
                if no_key and not ollama_alive_soon():
                    return "Auto would fall back to JARVIS Lite (no key, no Ollama)."
            from ..ai.llm import Message
            client = LLMClient.from_config({"provider": key, "model": model,
                                            "api_key": api_key, "base_url": base})
            out = client.chat([Message(role="user",
                                       content="Reply with the single word: online")])
            return f"OK — {client.describe()} replied: {out.content[:80]}"

        def done(text: str) -> None:
            self.result.setText(text)
            self.btn_test.setEnabled(True)

        def failed(text: str) -> None:
            self.result.setText(f"Failed: {text}")
            self.btn_test.setEnabled(True)

        # The widgets are touched in `done`/`failed`, which run on the GUI thread — the
        # old version wrote to them from the worker, which Qt does not allow.
        from .. import uiwork
        uiwork.run(work, done=done, failed=failed, name="arc-ai-test")

    # -- style ------------------------------------------------------------
    def _apply_style(self) -> None:
        th = self.theme
        self.setStyleSheet(f"""
            QDialog {{ background: {th.bg}; color: {th.text}; }}
            QLabel {{ color: {th.text}; }}
            QLabel#setupNote {{ color: {th.q('dim').lighter(150).name()}; font-size: 11px; }}
            QComboBox, QLineEdit {{ background: {th.panel}; color: {th.text};
                border: 1px solid {th.q('dim').name()}; border-radius: 8px; padding: 5px 8px; }}
            QComboBox:focus, QLineEdit:focus {{ border-color: {th.accent}; }}
            QComboBox QAbstractItemView {{ background: {th.panel}; color: {th.text};
                selection-background-color: {th.accent}; }}
            QPushButton {{ background: {th.q('accent').darker(115).name()}; color: #04090f;
                border: none; border-radius: 8px; padding: 7px 14px; font-weight: 600; }}
            QPushButton:disabled {{ background: {th.panel}; color: {th.dim}; }}
            QCheckBox {{ color: {th.text}; }}
        """)
