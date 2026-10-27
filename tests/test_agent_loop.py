"""End-to-end test of the agent loop against a fake OpenAI-compatible server.

Why this exists: the tool-calling path (model asks for a tool -> we run it ->
result goes back -> model answers) is the part most likely to break silently,
and it needs no API key or internet to test.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_agent_loop.py
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import os
import tempfile

# keep tests away from the real settings folder (see config.data_dir)
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk.ai.agent import Agent  # noqa: E402

TURN = {"n": 0}
SEEN_TOOL_RESULT: list[str] = []


class FakeBrain(BaseHTTPRequestHandler):
    """Turn 1: ask for the time tool. Turn 2: answer using the tool result."""

    def log_message(self, *args):  # keep the test output clean
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        msgs = body.get("messages", [])
        TURN["n"] += 1

        if TURN["n"] == 1:
            assert body.get("tools"), "client did not send tool schemas"
            payload = {"choices": [{"message": {
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "call_1", "type": "function",
                                "function": {"name": "time", "arguments": "{}"}}]}}]}
        else:
            for m in msgs:
                if m.get("role") == "tool":
                    SEEN_TOOL_RESULT.append(m.get("content", ""))
            payload = {"choices": [{"message": {
                "role": "assistant",
                "content": "According to the machine clock, it is " +
                           (SEEN_TOOL_RESULT[-1] if SEEN_TOOL_RESULT else "unknown") + "."}}]}

        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeBrain)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"fake brain on 127.0.0.1:{port}")

    QApplication.instance() or QApplication(sys.argv[:1])   # Qt needs one app object
    cfg = {"ai": {"enabled": True, "provider": "custom", "api_key": "test",
                  "base_url": f"http://127.0.0.1:{port}/v1", "model": "fake",
                  "voice": False}}

    agent = Agent(cfg)
    agent.context_fn = lambda: "Machine context: test rig."
    got: dict[str, str] = {}
    used: list[tuple] = []
    agent.reply.connect(lambda t: got.setdefault("text", t))
    agent.tool_used.connect(lambda n, a, r: used.append((n, a, r)))

    loop = QEventLoop()
    agent.reply.connect(lambda *_: loop.quit())
    agent.error.connect(lambda e: got.setdefault("error", e))
    agent.error.connect(lambda *_: loop.quit())
    QTimer.singleShot(20_000, loop.quit)

    agent.ask("what time is it?")
    loop.exec()
    server.shutdown()

    print("\n--- results ---")
    print("brain :", agent.describe())
    print("tools :", used)
    print("answer:", got.get("text"))
    if got.get("error"):
        print("error :", got["error"])

    ok = (not got.get("error")
          and len(used) == 1 and used[0][0] == "time"
          and "it is" in (got.get("text") or "").lower())
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
