"""Streaming speech — the answer is spoken while it is still being written.

The point of this file is a number: **time to first spoken word**. Serial says
nothing until the model finishes (3.7 s on a 0.5B); streaming says the first
sentence as soon as it exists (0.6 s in the same run).

Locks four things:

  1. the sentence splitter never cuts a word in half and never speaks a fragment;
  2. a real SSE response is consumed token by token, and the first delta arrives
     well before the end of the same answer;
  3. the voice queue *appends* instead of cancelling, so sentence 2 does not
     silence sentence 1, and one `on_done` fires at the end (the mic opens once);
  4. a server that ignores `stream: true` still produces a full answer.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_stream.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-stream-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk.ai import agent as agent_mod  # noqa: E402
from arcdesk.ai import voice as V  # noqa: E402
from arcdesk.ai.agent import split_ready  # noqa: E402
from arcdesk.ai.llm import LLMClient  # noqa: E402

ANSWER = "Nifty is down half a percent. Gold is flat. Your editor is open."


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<46} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


class StreamBrain(BaseHTTPRequestHandler):
    delay = 0.05
    honour_stream = True

    def log_message(self, *args):
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if not (self.honour_stream and body.get("stream")):
            payload = {"choices": [{"message": {"role": "assistant", "content": ANSWER}}],
                       "usage": {"total_tokens": 9}}
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for word in ANSWER.split(" "):
            chunk = {"choices": [{"delta": {"content": word + " "}}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
            time.sleep(self.delay)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class ToolBrain(BaseHTTPRequestHandler):
    """A server that behaves like llama.cpp: `tools` + `stream: true` = no tool call.

    This is not hypothetical. On llama.cpp's llama-server (the default local engine)
    a streaming request quietly ignores the tool schema and the model answers from
    memory — the single worst failure mode in the whole app, because it looks like a
    correct answer. The agent must therefore plan without streaming there.
    """

    seen: list[dict] = []

    def log_message(self, *args):
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        ToolBrain.seen.append(body)
        messages = body.get("messages") or []
        already_ran = any(m.get("role") == "tool" for m in messages)
        wants_stream = bool(body.get("stream"))
        if body.get("tools") and wants_stream and not already_ran:
            # the bug: schema dropped, no tool call, confident prose instead
            content = "Nifty is up about one percent today."
            if True:
                payload = {"choices": [{"message": {"role": "assistant", "content": content}}]}
                raw = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            return
        if not already_ran:
            payload = {"choices": [{"message": {
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "call_1", "type": "function",
                                "function": {"name": "time", "arguments": "{}"}}]}}]}
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        # after the tool ran: stream the wrap-up, like a real server would
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for word in "It is half past four.".split(" "):
            chunk = {"choices": [{"delta": {"content": word + " "}}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.02)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class Recorder(V.Voice):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.said: list[str] = []

    def _speak_blocking(self, text: str, wav: str = "") -> bool:
        self.said.append(text)
        time.sleep(0.01)
        return True


def main() -> int:
    ok = True
    QApplication.instance() or QApplication([sys.argv[0]])

    print("1) the splitter hands over whole sentences only")
    head, tail = split_ready("Nifty is down half a percent. Gold is flat. Gold i")
    ok &= check("first sentence complete", head, "Nifty is down half a percent.")
    ok &= check("tail kept for later", tail.strip(), "Gold is flat. Gold i")
    ok &= check("nothing ready yet", split_ready("Nifty is")[0], "")
    word, rest = split_ready("x" * 300)
    ok &= check("a giant token is passed through whole", (len(word), rest), (300, ""))
    ok &= check("never cut mid-word", split_ready("word " * 80)[0][-1], "d")

    print("2) a real SSE stream is read token by token")
    server = ThreadingHTTPServer(("127.0.0.1", 0), StreamBrain)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = LLMClient("custom", f"http://127.0.0.1:{port}/v1", "fake", "", timeout=30)

    stamps: list[float] = []
    t0 = time.time()
    answer = client.chat_stream(
        [agent_mod.Message("user", "market?")], None,
        on_delta=lambda piece: stamps.append(time.time() - t0))
    total = time.time() - t0
    ok &= check("answer complete", answer.content, ANSWER)
    ok &= check("deltas arrived", len(stamps) > 5, True)
    ok &= check("first delta was early", stamps[0] < total * 0.5, True)
    print(f"      first word at {stamps[0]:.2f}s · end at {total:.2f}s "
          f"· {len(stamps)} deltas")

    print("3) the voice queue appends instead of cancelling")
    v = Recorder({"ai": {"voice": True}})
    done: list[int] = []
    v.speak("First sentence here.", append=True, on_done=lambda: done.append(1))
    v.speak("Second sentence here.", append=True)
    v.close_stream()
    v.wait_idle(timeout=10)
    ok &= check("both sentences spoken", len(v.said), 2)
    ok &= check("in order", v.said[0].startswith("First"), True)
    ok &= check("one on_done at the end", done, [1])

    print("4) stop() still silences a stream mid-flight")
    v2 = Recorder({"ai": {"voice": True}})
    v2.speak("One sentence. Two sentence.", append=True)
    time.sleep(0.02)
    v2.stop()
    v2.close_stream()
    v2.wait_idle(timeout=10)
    ok &= check("not speaking afterwards", v2.speaking, False)

    print("5) the agent speaks while the model is still writing")
    ag = agent_mod.Agent({"ai": {"enabled": True, "provider": "custom", "voice": False,
                                 "stream": True, "fast_path": False}, "cost": {}})
    ag.client = LLMClient("custom", f"http://127.0.0.1:{port}/v1", "fake", "", timeout=30)
    ag.brain = "llm"
    ag._resolve_brain = lambda: None          # the test decides the brain, not the config
    spoken: list[str] = []
    replies: list[str] = []
    ag.speak_partial.connect(lambda t: spoken.append(t))
    ag.reply.connect(lambda t: replies.append(t))
    t0 = time.time()
    ag.ask("tell me about the sea")
    deadline = time.time() + 20
    # agent signals cross threads, so they need an event loop to be delivered
    while not replies and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.02)
    ok &= check("reply arrived", bool(replies), True)
    ok &= check("spoken in several pieces", len(spoken) >= 2, True)
    ok &= check("nothing lost between pieces", " ".join(spoken).split(), ANSWER.split())

    print("6) llama.cpp's schema drop is handled")
    ok &= check("llama.cpp is flagged as no tool streaming",
                LLMClient("llama.cpp", "http://127.0.0.1:1/v1", "x").supports_tool_stream(),
                False)
    ok &= check("a normal OpenAI-compatible server keeps streaming tools",
                client.supports_tool_stream(), True)
    ToolBrain.seen = []
    tserver = ThreadingHTTPServer(("127.0.0.1", 0), ToolBrain)
    threading.Thread(target=tserver.serve_forever, daemon=True).start()
    ag2 = agent_mod.Agent({"ai": {"enabled": True, "provider": "llama.cpp", "voice": False,
                                  "stream": True, "fast_path": False}, "cost": {}})
    ag2.client = LLMClient("llama.cpp", f"http://127.0.0.1:{tserver.server_address[1]}/v1",
                           "fake", "", timeout=30)
    ag2.brain = "llm"
    ag2._resolve_brain = lambda: None
    got2: list[str] = []
    ag2.reply.connect(lambda t: got2.append(t))
    ag2.ask("what time is it")
    deadline = time.time() + 20
    while not got2 and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.02)
    for i, req in enumerate(ToolBrain.seen):
        print(f"      round {i}: stream={req.get('stream')} tools={len(req.get('tools') or [])} "
              f"msgs={[m.get('role') for m in req.get('messages') or []]}")
    first = ToolBrain.seen[0] if ToolBrain.seen else {}
    ok &= check("the planning round is sent without stream",
                bool(first.get("stream")) if first else None, False)
    ok &= check("the tool actually ran",
                any(m.get("role") == "tool" for m in
                    (ToolBrain.seen[1].get("messages") if len(ToolBrain.seen) > 1 else [])),
                True)
    ok &= check("and the real answer came back",
                any("half past" in t for t in got2), True)
    tserver.shutdown()

    print("7) a server that ignores stream:true still answers")
    StreamBrain.honour_stream = False
    got: list[str] = []
    ans = client.chat_stream([agent_mod.Message("user", "hi")], None,
                             on_delta=got.append)
    ok &= check("full content", ans.content, ANSWER)
    ok &= check("deltas fired once", len(got), 1)
    server.shutdown()

    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
