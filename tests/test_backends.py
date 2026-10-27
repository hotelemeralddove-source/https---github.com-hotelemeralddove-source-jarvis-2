"""Local open-source backend detection, proven without installing any of them.

Stands up a fake OpenAI-compatible server on llama.cpp's default port and checks
that Arc Desk finds it, picks its model, and would use it as the brain.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_backends.py
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

from arcdesk.ai import backends  # noqa: E402
from arcdesk.ai.llm import LLMClient  # noqa: E402

PORT = 8080          # llama.cpp / LocalAI default


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        return

    def do_GET(self):                       # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            body = json.dumps({"data": [{"id": "qwen2.5-3b-instruct.gguf"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def main() -> int:
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Fake)
    except OSError as exc:
        print(f"SKIP: port {PORT} busy ({exc})")
        return 0
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    # Hermetic: this test owns port 8080, and only port 8080. A laptop that happens to
    # run Ollama (11434) or LM Studio is not part of the experiment - with the full
    # BACKENDS list, `best_local` would honestly prefer the real Ollama, and a healthy
    # build would read as broken. Restore the list before finishing.
    real_backends = backends.BACKENDS
    backends.BACKENDS = tuple(b for b in real_backends
                              if b.key == "llamacpp" and b.port == PORT)
    found = backends.probe()
    names = [d.backend.key for d in found]
    print("detected   :", names)
    best = backends.best_local()
    print("best_local :", best.describe() if best else None)

    ok_hits = any(n in ("llamacpp", "localai") for n in names)

    # the client must build itself from the detected backend
    client = LLMClient.from_config({"provider": "auto", "api_key": "", "model": ""})
    described = client.describe()
    print("auto brain :", described)
    print("provider   :", client.provider)

    ok_pick = client.provider in ("llamacpp", "localai") and "qwen2.5" in described
    ok_health = backends.quick_health(f"http://127.0.0.1:{PORT}/v1")[0]

    srv.shutdown()
    backends.BACKENDS = real_backends
    ok = ok_hits and ok_pick and ok_health
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
