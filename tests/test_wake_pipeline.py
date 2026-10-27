"""Proves the wake-word pipeline end to end without a microphone.

    app window listening  <--  arc_daemon.py --simulate "system report"

The daemon part is the real daemon script, opening a real TCP socket and sending
the real protocol messages. Only the audio capture is bypassed, which is exactly
the part a CI box or a laptop without a mic cannot provide.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_wake_pipeline.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import os
import tempfile

# keep tests away from the real settings folder (see config.data_dir)
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk import config  # noqa: E402
from arcdesk.widgets.window import MainWindow  # noqa: E402

PORT = 8899


def main() -> int:
    app = QApplication(sys.argv[:1])
    cfg = config.load()
    cfg["mode"] = "chill"
    cfg["window"] = {"w": 1000, "h": 690, "x": 20, "y": 20}
    cfg["ai"] = {"enabled": True, "provider": "lite", "voice": False}
    cfg["wake"] = {"enabled": True, "phrase": "hey jarvis", "engine": "auto",
                   "port": PORT, "command_seconds": 7, "autostart_daemon": False}

    win = MainWindow(cfg)
    win.show()
    for _ in range(10):
        app.processEvents()

    print("wake server listening:", win.wake_server.listening)
    if not win.wake_server.listening:
        print("FAIL: wake server did not start")
        return 1

    got = {"woke": False, "text": "", "reply": ""}
    win.wake_server.woke.connect(lambda: got.__setitem__("woke", True))
    win.wake_server.command.connect(lambda t: got.__setitem__("text", t))
    win.agent.reply.connect(lambda t: got.__setitem__("reply", t))

    daemon = Path(__file__).resolve().parents[1] / "arc_daemon.py"
    proc = subprocess.Popen([sys.executable, str(daemon), "--port", str(PORT),
                             "--simulate", "system report"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    loop = QEventLoop()
    done = {"v": False}

    def check():
        if got["reply"] and not done["v"]:
            done["v"] = True
            loop.quit()

    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(150)
    QTimer.singleShot(25_000, loop.quit)
    loop.exec()
    timer.stop()

    try:
        out = proc.communicate(timeout=5)[0]
    except Exception:
        proc.kill()
        out = ""
    win.wake_daemon.stop()

    print("\n--- results ---")
    print("daemon said :", (out or "").strip().replace("\n", " | ")[:200])
    print("wake heard  :", got["woke"])
    print("command     :", got["text"])
    print("arc replied :", got["reply"][:160])

    ok = got["woke"] and got["text"] == "system report" and bool(got["reply"])
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
