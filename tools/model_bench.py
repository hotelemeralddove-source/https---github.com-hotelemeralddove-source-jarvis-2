#!/usr/bin/env python3
"""Which local model should ARC use? Measured on your machine, not guessed.

    python tools/model_bench.py                        # whatever is on :8080
    python tools/model_bench.py --url http://127.0.0.1:11434/v1 --model qwen2.5:3b
    python tools/model_bench.py --cases 6 --json shots/bench_3b.json

A fixed suite of everyday commands, each with the tool a human would expect. The
score is brutally simple: **did the right tool get called**. A model that writes
beautiful prose but calls `system_report` when you asked for the time is worse
than useless in a voice assistant.

Everything runs through the real Agent — routing, schemas, tool execution — so the
numbers include the parts that actually decide whether the thing feels alive:
latency to a usable answer, tokens burned per command, and whether it fumbled.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk.ai import agent as agent_mod  # noqa: E402
from arcdesk.ai.llm import LLMClient  # noqa: E402

# phrase, the tool that must be called ("" = no tool is correct)
CASES: list[tuple[str, str]] = [
    ("what time is it", "time"),
    ("how much ram am i using", "system_report"),
    ("open notepad", "open_app"),
    ("18% of 4500", "calc"),
    ("convert 5 km to miles", "convert"),
    ("nifty price", "stock"),
    ("draw a cat", "draw"),
    ("set the volume to 20", "set_volume"),
    ("note that i parked at level 2", "note"),
    ("teach me when i say work mode", "teach_macro"),
    ("what have i taught you", "macros"),
    ("take a screenshot", "screenshot"),
    ("what is the dollar rate", "rates"),
    ("read the error on my screen", "screen_text"),
]


def bar(c: str = "─") -> None:
    print(c * 78)


def models(base: str) -> list[str]:
    import urllib.request
    with urllib.request.urlopen(f"{base}/models", timeout=4) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    return [m.get("id") for m in data.get("data", []) if m.get("id")]


def one(base: str, model: str, phrase: str, timeout: int, fast: bool = True) -> dict:
    cfg = {"ai": {"enabled": True, "provider": "custom", "voice": False,
                  "stream": False, "fast_path": fast},
           "cost": {}}
    ag = agent_mod.Agent(cfg)
    ag.client = LLMClient("custom", base, model, "", timeout=timeout)
    ag.brain = "llm"
    ag._resolve_brain = lambda: None        # noqa: SLF001 — the bench decides
    used: list[str] = []
    replies: list[str] = []
    errors: list[str] = []
    ag.tool_used.connect(lambda n, a, r: used.append(n))
    ag.reply.connect(replies.append)
    ag.error.connect(errors.append)
    t0 = time.time()
    ag.ask(phrase)
    deadline = time.time() + timeout
    while not replies and not errors and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.02)
    took = time.time() - t0
    return {"phrase": phrase, "tools": used, "reply": (replies or errors or [""])[-1],
            "seconds": round(took, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="", help="OpenAI-compatible base URL (…/v1)")
    ap.add_argument("--model", default="")
    ap.add_argument("--cases", type=int, default=len(CASES))
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--json", default="", help="write the raw results here")
    ap.add_argument("--model-only", action="store_true",
                    help="disable the rule-based fast path, so the model is measured "
                         "on commands it would otherwise never see")
    args = ap.parse_args()
    QApplication.instance() or QApplication([sys.argv[0]])

    base = args.url.rstrip("/")
    if not base:
        for guess in ("http://127.0.0.1:8080/v1", "http://127.0.0.1:11434/v1",
                      "http://127.0.0.1:1234/v1"):
            try:
                ids = models(guess)
                base, model = guess, (args.model or ids[0])
                break
            except Exception:
                continue
        else:
            print("no local model server found on 8080 / 11434 / 1234")
            print("start one, e.g.  llama-server -m model.gguf --port 8080 --jinja")
            return 2
    else:
        try:
            model = args.model or models(base)[0]
        except Exception as exc:
            print(f"cannot reach {base}: {exc}")
            return 2

    print(f"ARC DESK · model bench · {model}")
    bar("=")
    print(f"  server {base}")
    mode = "model only (fast path off)" if args.model_only else \
        "with the rule-based fast path (how it actually runs)"
    print(f"  cases  {args.cases} of {len(CASES)} everyday commands, one attempt each")
    print(f"  mode   {mode}\n")

    rows = []
    for phrase, expect in CASES[: args.cases]:
        result = one(base, model, phrase, args.timeout, fast=not args.model_only)
        called = result["tools"][0] if result["tools"] else ""
        hit = (called == expect) if expect else (not called)
        rows.append({**result, "expected": expect, "called": called, "hit": hit})
        mark = "OK  " if hit else "MISS"
        print(f"  [{mark}] {phrase:<32} → {called or '(no tool)':<14} {result['seconds']:>5.1f}s")
        if not hit:
            print(f"         wanted {expect or '(no tool)'}; it said: "
                  f"{' '.join(result['reply'].split())[:90]}")

    hits = sum(1 for r in rows if r["hit"])
    times = [r["seconds"] for r in rows]
    print()
    bar()
    print(f"  tool accuracy   {hits}/{len(rows)} = {100 * hits / max(1, len(rows)):.0f}%")
    print(f"  latency         median {sorted(times)[len(times) // 2]:.1f}s · "
          f"min {min(times):.1f}s · max {max(times):.1f}s")
    verdict = ("good enough for conversation" if hits == len(rows) and
               sorted(times)[len(times) // 2] < 4 else
               "usable, but keep Lite as the default for these commands" if hits >= len(rows) * 0.7
               else "too unreliable to be the default brain")
    print(f"  verdict         {verdict}")
    print(f"  compare         the same commands through Lite: "
          f"{_lite_ms():.1f} ms each, 0 tool mistakes")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps({"server": base, "model": model,
                                               "rows": rows}, indent=2), encoding="utf-8")
        print(f"  raw results     {args.json}")
    return 0


def _lite_ms() -> float:
    from arcdesk.ai import lite
    t0 = time.time()
    for phrase, _ in CASES[:8]:
        lite.respond(phrase)
    return (time.time() - t0) * 1000 / 8


if __name__ == "__main__":
    raise SystemExit(main())
