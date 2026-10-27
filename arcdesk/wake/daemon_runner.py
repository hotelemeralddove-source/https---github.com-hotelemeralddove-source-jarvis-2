"""Start / stop the voice daemon as a child process of the app.

Rules:
  * never block the UI on spawn (it is a Popen, no wait)
  * no console window on Windows
  * the daemon is terminated whenever the app really quits, so we do not leave
    a microphone open behind the user's back
  * if the app is frozen into an exe, the daemon must be frozen too; we say so
    instead of silently failing
"""
from __future__ import annotations

import os
import subprocess

from .. import quiet
from pathlib import Path

from .. import config
from ..paths import app_dir, daemon_command


class DaemonRunner:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.last_error = ""

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def pid(self) -> int | None:
        return self.proc.pid if self.running else None

    def _script(self) -> Path:
        return app_dir() / "arc_daemon.py"

    def start(self, port: int, phrase: str, engine: str = "auto",
              exit_phrase: str = "bye jarvis",
              launcher_app: str | None = None,
              converse: bool = False, turns: int = 6,
              voice_lock: bool = False,
              command_seconds: float | None = None,
              silence_seconds: float | None = None,
              max_command_seconds: float | None = None) -> bool:
        if self.running:
            return True
        extra = ["--converse", "--converse-turns", str(max(1, int(turns)))] if converse else []
        if voice_lock:
            extra += ["--voice-lock"]
        # The Settings page had these numbers and never passed them on, so changing
        # "Command window" did nothing at all. Now it does.
        if command_seconds:
            extra += ["--command-seconds", f"{float(command_seconds):g}"]
        if silence_seconds:
            extra += ["--silence-seconds", f"{float(silence_seconds):g}"]
        if max_command_seconds:
            extra += ["--max-command-seconds", f"{float(max_command_seconds):g}"]
        cmd, kwargs = daemon_command(port, phrase, engine, exit_phrase, launcher_app,
                                     extra=extra)
        exe = Path(cmd[0])
        if not exe.exists():
            self.last_error = (f"voice backend missing: {exe.name}. "
                               "In a packaged build this is ArcDeskVoice.exe next to the app.")
            return False
        try:
            self.proc = quiet.popen(
                cmd, cwd=str(app_dir()), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}, **kwargs)
            return True
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.proc = None
            return False

    def stop(self) -> None:
        if not self.running:
            self.proc = None
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def rss_mb(self) -> float:
        """Own RAM of the daemon, so the HUD can be honest about the cost."""
        pid = self.pid()
        if pid is None:
            return 0.0
        try:
            import psutil
            return psutil.Process(pid).memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0


def model_path() -> Path:
    return config.data_dir() / "vosk-model-small-en-us-0.15"
