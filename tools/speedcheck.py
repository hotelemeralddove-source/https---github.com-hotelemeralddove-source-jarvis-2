#!/usr/bin/env python3
"""How fast does it actually answer? — measured, on this machine, right now.

    python tools/speedcheck.py
    python tools/speedcheck.py --n 200 --json

The user's points 3 and 4 were *"respond panra time seekiram irukanum"* and *"ans panrathuku
romba time yeduka koodathu"*. Those are numbers, so this file produces numbers and nothing
else. Three separate things get measured, because they have three different causes:

  1. **Lite path** — typing a command that the offline rule engine understands. No model,
     no network. This is the floor, and the floor should be milliseconds.
  2. **Routing** — how long it takes to decide which tools even apply before any model
     sees the request (the token saving that keeps a small local model fast).
  3. **Tool call** — the round trip of an actual tool (a cheap one: exact arithmetic).

Honest framing, because this is the part people lie about:
  * Every number below includes the work, not a cached constant.
  * p50 matters more than the mean; one slow outlier is not "average" anything.
  * A local LLM's speed depends on the model and the CPU and is NOT measured here — that
    is `tools/bench.py` / `tools/live.py` on a machine with a model installed. Saying
    "instant" because Lite is instant would be a lie, so this tool refuses to do it.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-speed-"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PHRASES = [
    "what is the time",
    "open notepad",
    "what is using my ram",
    "volume 40",
    "take a screenshot",
    "note buy milk",
    "calculate 1234*0.18+56",
    "how many states in india",
    "start a project called speed test",
    "where do my files save",
    "why is my laptop slow",
    "find my report",
    "what is 18% of 4500",
    "how is my cpu doing",
    "play ilaya nila",
    "explain this error: ModuleNotFoundError",
]


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1)))))
    return ordered[k]


def timed(fn, n: int) -> list[float]:
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000)     # ms
    return out


def main(argv: list[str]) -> int:
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 20
    as_json = "--json" in argv

    from arcdesk.ai import lite, select, tools

    # warm the imports so the first measurement is not "python imported 40 modules"
    lite.respond("what is the time")

    report: dict = {"phrases": len(PHRASES), "runs_each": n}

    # 1. Lite end-to-end: understand the sentence + build the tool calls
    lite_ms: list[float] = []
    per_phrase = []
    for phrase in PHRASES:
        samples = timed(lambda p=phrase: lite.respond(p), max(1, n // 4))
        lite_ms.extend(samples)
        per_phrase.append({"phrase": phrase,
                           "p50_ms": round(statistics.median(samples), 2)})

    # 2. routing: how many tools a request narrows to, and how long that takes
    route_ms: list[float] = []
    narrowed: list[int] = []
    try:
        for phrase in PHRASES:
            def run(p=phrase):
                picked = select.names(p, tools.TOOLS, k=8)
                narrowed.append(len(picked))
            route_ms.extend(timed(run, max(1, n // 4)))
    except Exception as exc:                              # never fail a speed report
        report["routing_error"] = f"{type(exc).__name__}: {exc}"

    # 3. one real tool call (exact arithmetic — cheap, deterministic, no I/O)
    tool_ms = timed(lambda: tools.call("calc", {"expression": "(1234*0.18)+56"}), n)

    # 4. the vault: the write that happens on every single answer
    from arcdesk import vault
    vault.create("speed test")
    vault_ms = timed(lambda: vault.checkpoint("speed check"), n)

    report.update({
        "lite": {"p50": round(statistics.median(lite_ms), 2),
                 "p95": round(pct(lite_ms, 95), 2),
                 "max": round(max(lite_ms), 2), "samples": len(lite_ms)},
        "routing": {"p50": round(statistics.median(route_ms), 2) if route_ms else None,
                    "tools_narrowed_to": (round(statistics.mean(narrowed), 1)
                                          if narrowed else None),
                    "total_tools": len(tools.TOOLS)},
        "tool_call_calc": {"p50": round(statistics.median(tool_ms), 2),
                           "max": round(max(tool_ms), 2)},
        "vault_checkpoint": {"p50": round(statistics.median(vault_ms), 2),
                             "max": round(max(vault_ms), 2)},
        "slowest_phrases": sorted(per_phrase, key=lambda r: -r["p50_ms"])[:3],
    })

    if as_json:
        print(json.dumps(report, indent=1))
        return 0

    print("ARC DESK · speed check  (this machine, this run)")
    print("=" * 70)
    print(f"  Lite path (offline, no model, no network)   {len(lite_ms):>4} runs")
    print(f"      p50 {report['lite']['p50']:>6.2f} ms   "
          f"p95 {report['lite']['p95']:>6.2f} ms   max {report['lite']['max']:>6.2f} ms")
    print("      slowest phrases: " + ", ".join(
        f"'{r['phrase'][:28]}' {r['p50_ms']:.1f} ms" for r in report["slowest_phrases"]))
    if report["routing"]["p50"] is not None:
        print(f"  Routing a request to the right tools        p50 "
              f"{report['routing']['p50']:.2f} ms")
        print(f"      narrows {report['routing']['total_tools']} tools to about "
              f"{report['routing']['tools_narrowed_to']:.0f} before any model reads them")
    print(f"  A real tool call (exact arithmetic)         p50 "
          f"{report['tool_call_calc']['p50']:.2f} ms")
    print(f"  Vault checkpoint (runs on every answer)     p50 "
          f"{report['vault_checkpoint']['p50']:.2f} ms")

    print("\nWhat this does NOT claim:")
    print("  · that a local LLM answers in milliseconds. A 0.5B model on 2 CPU cores takes")
    print("    seconds; that is measured by tools/live.py on a machine that has one.")
    print("  · that the first answer after a cold start is this fast — the import cost is")
    print("    real and is measured by tools/smoke_firstrun.py, not hidden here.")
    print("\nThe design that keeps it quick, in order of effect:")
    print("  1. the offline Lite brain handles the shapes people actually repeat,")
    print("  2. routing hands the model 4-9 tools instead of " + str(len(tools.TOOLS)) + ",")
    print("  3. speech starts on the first sentence, not the last,")
    print("  4. slow work (media, disk scans, indexing) runs off the GUI thread.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
