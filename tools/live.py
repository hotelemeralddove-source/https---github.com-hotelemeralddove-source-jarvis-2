#!/usr/bin/env python3
"""Run the real agent loop against a real local model, with the wire visible.

    python tools/live.py                          # auto-detect a local engine
    python tools/live.py --url http://127.0.0.1:8080/v1 --model qwen2.5-0.5b
    python tools/live.py "draw me a cat and tell me the time"
    python tools/live.py --json                   # machine-readable summary

Unlike `tools/think.py` (which replays a recording), this talks to an actual
OpenAI-compatible server — llama.cpp's `llama-server`, Ollama, LM Studio, vLLM,
whatever you have on localhost. It prints every round: what was sent, how long it
took, what the model asked for, what the tool returned, and what it finally said.

Nothing here is required by the app. It exists so that claims about latency and
tool calling can be checked instead of asserted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk.ai import agent as agent_mod  # noqa: E402
from arcdesk.ai import lite, tools  # noqa: E402
from arcdesk.ai.llm import LLMClient, Message  # noqa: E402

W = 74
CANDIDATES = [
    ("llama.cpp", "http://127.0.0.1:8080/v1"),
    ("Ollama", "http://127.0.0.1:11434/v1"),
    ("LM Studio", "http://127.0.0.1:1234/v1"),
    ("LocalAI", "http://127.0.0.1:8080/v1"),
]


def bar(c: str = "─") -> None:
    print(c * W)


def say(label: str, value: str) -> None:
    print(f"    {label:<18} {value}")


def clip(s: str, n: int = 100) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def feel(seconds: float) -> str:
    """Honest wording for a latency, so a slow answer is not dressed up."""
    if seconds < 1.0:
        return "instant"
    if seconds < 4.0:
        return "snappy"
    if seconds < 10.0:
        return "slow but usable for a one-off"
    return "too slow for conversation"


class WireClient:
    """Wraps the real client and records every request/response."""

    def __init__(self, inner: LLMClient):
        self.inner = inner
        self.provider = inner.provider
        self.base_url = inner.base_url
        self.model = inner.model
        self.rounds: list[dict] = []

    def describe(self) -> str:
        return self.inner.describe()

    def chat(self, messages: list[Message], schema=None) -> Message:
        sent = [m.as_dict() for m in messages]
        nbytes = len(json.dumps(sent))
        t0 = time.time()
        answer = self.inner.chat(messages, schema)
        dt = time.time() - t0
        self.rounds.append({
            "messages": len(sent),
            "request_bytes": nbytes,
            "tools_offered": len(schema or []),
            "seconds": round(dt, 2),
            "tool_calls": answer.tool_calls,
            "content": answer.content,
            "usage": answer.usage,
            "prompt_preview": clip(sent[-1].get("content", ""), 90),
        })
        return answer


def _models(base: str) -> list[str]:
    with urllib.request.urlopen(f"{base}/models", timeout=4) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
    ids += [m.get("model") for m in data.get("models", []) if m.get("model")]
    return [i for i in dict.fromkeys(ids) if i]


def discover(url: str, model: str, wait: float = 25.0) -> tuple[str, str, list[str]]:
    """Find a server and its models.

    A model that is still loading answers nothing, so this retries instead of
    declaring the server absent — the difference between "not running" and
    "not ready yet" matters when you start both from the same script.
    """
    tries = [url] if url else [u for _, u in CANDIDATES]
    started = time.time()
    announced = False
    while True:
        for base in tries:
            try:
                ids = _models(base)
                if ids:
                    return base, model or ids[0], ids
            except Exception:
                continue
        if time.time() - started >= wait:
            return "", "", []
        if not announced:
            print(f"    waiting for a model server (up to {wait:.0f}s)…")
            announced = True
        time.sleep(1.5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", nargs="*")
    ap.add_argument("--url", default="", help="OpenAI-compatible base URL, e.g. .../v1")
    ap.add_argument("--model", default="", help="model id; empty = ask the server")
    ap.add_argument("--json", action="store_true", help="print a JSON summary at the end")
    ap.add_argument("--no-tools", action="store_true", help="send no tool schemas (compare)")
    ap.add_argument("--core", action="store_true",
                    help="send only the spoken-sized tool subset (agent ai.core_tools)")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="run the same phrase N times and report consistency")
    args = ap.parse_args()
    QApplication.instance() or QApplication([sys.argv[0]])

    text = " ".join(args.prompt).strip() or \
        "what time is it, and how much ram am i using?"

    base, model, ids = discover(args.url, args.model)
    print(f'ARC DESK · live model run · "{clip(text, 60)}"')
    bar("=")
    if not base:
        print("    no local model answered on 8080 / 11434 / 1234.")
        print("    start one, e.g.:  llama-server -m model.gguf --port 8080 --jinja")
        return 2
    say("server", base)
    say("model", f"{model}   ({len(ids)} available: {', '.join(ids[:3])})")

    schema = [] if args.no_tools else tools.schemas(core_only=args.core)
    say("tools offered", str(len(schema)) or "none")

    def once() -> dict:
        inner = LLMClient("custom", base, model, "", timeout=300)
        client = WireClient(inner)
        cfg = {"ai": {"enabled": True, "provider": "custom", "voice": False,
                      "core_tools": bool(args.core)}, "cost": {}}
        ag = agent_mod.Agent(cfg)
        ag.brain, ag.client = "llm", client
        out = {"replies": [], "used": [], "client": client}
        ag.reply.connect(lambda t: out["replies"].append(t))
        ag.tool_used.connect(lambda n, a, r: out["used"].append((n, a, r)))
        t0 = time.time()
        ag._history.append(Message(role="user", content=text))
        ag._run_llm()
        out["seconds"] = time.time() - t0
        return out

    if args.repeat > 1:
        rows = []
        for i in range(args.repeat):
            r = once()
            rounds = r["client"].rounds
            tok = sum((x["usage"] or {}).get("completion_tokens", 0) for x in rounds)
            secs = sum(x["seconds"] for x in rounds)
            rows.append((i + 1, [n for n, _, _ in r["used"]], r["seconds"],
                         tok / secs if secs else 0, clip(r["replies"][-1] if r["replies"] else "", 52)))
            print(f"    run {i + 1}: {len(r['used'])} tool call(s) · "
                  f"{r['seconds']:.1f}s · {rows[-1][3]:.1f} tok/s")
        print()
        bar()
        called = sum(1 for _, used, _, _, _ in rows if used)
        say("tool calls", f"{called}/{len(rows)} runs used a tool")
        say("latency", f"min {min(r[2] for r in rows):.1f}s · "
                       f"max {max(r[2] for r in rows):.1f}s")
        say("verdict", "consistent" if called == len(rows) else "inconsistent — plan for it")
        if args.json:
            print(json.dumps({"server": base, "model": model,
                              "runs": [{"tools": u, "seconds": round(sec, 2),
                                        "reply": rep} for _, u, sec, _, rep in rows]},
                             indent=2))
        return 0

    try:
        r = once()
    except Exception as exc:
        print(f"\n    FAILED: {type(exc).__name__}: {exc}")
        return 1
    client, replies, used = r["client"], r["replies"], r["used"]
    t0 = time.time() - r["seconds"]

    # -- print every round as it happened -----------------------------
    for i, r in enumerate(client.rounds, 1):
        print(f"\n[round {i}] {r['messages']} messages · {r['request_bytes']} bytes · "
              f"{r['tools_offered']} tools → {r['seconds']}s ({feel(r['seconds'])})")
        u = r["usage"] or {}
        if u:
            tok = u.get("completion_tokens") or 0
            say("tokens", f"prompt {u.get('prompt_tokens', '?')} · "
                          f"completion {tok}"
                          + (f" · {tok / r['seconds']:.1f} tok/s" if r["seconds"] else ""))
        if r["tool_calls"]:
            for c in r["tool_calls"]:
                f = c.get("function", {})
                say("asks for", f'{f.get("name")}({f.get("arguments")})')
        else:
            say("answers", clip(r["content"]) or "(empty)")

    if used:
        print(f"\n[executed] {len(used)} tool call(s), real, on this machine")
        for n, a, res in used:
            say(n, clip(res, 96))

    print("\n[reply]")
    for line in (replies[-1] if replies else "(none)").splitlines() or [""]:
        print("    " + line)

    total = time.time() - t0
    print()
    bar()
    say("end to end", f"{total:.2f}s · {feel(total)}")
    say("rounds", str(len(client.rounds)))

    # -- contrast: the same phrase through Lite, no model -----------------
    lt0 = time.time()
    spoken, calls = lite.respond(text)
    lite_s = time.time() - lt0
    say("lite, same text", f"{lite_s * 1000:.1f} ms · "
                           f"{len(calls)} tool call(s) · "
                           f"{'matched' if calls else 'no match, it would say so'}")

    if args.json:
        print(json.dumps({
            "server": base, "model": model, "prompt": text,
            "rounds": client.rounds, "tools_used": [n for n, _, _ in used],
            "reply": replies[-1] if replies else "", "seconds": round(total, 2),
            "lite_ms": round(lite_s * 1000, 2),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
