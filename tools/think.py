#!/usr/bin/env python3
"""Trace the *thinking* half: prompt → tool calls → results → answer.

    python tools/think.py
    python tools/think.py "how much ram am i using, and draw me a cat"
    python tools/think.py --confirm "shut down the pc"

`tools/explain.py` shows how words get in. This shows what ARC does with them
once they arrive: exactly what the model is given, what it decides, what the app
does with that decision, and where the answer comes out.

The model here is scripted, not connected — that is the point. The *agent loop*
is real code (`Agent._run_llm`, `Agent._execute`, `lite.respond`,
`lite.summarise_tool_result`), so what you see is the real control flow, with the
one unpredictable part (the model's words) replaced by a recording.
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

from arcdesk import config  # noqa: E402
from arcdesk.ai import agent as agent_mod  # noqa: E402
from arcdesk.ai import lite, tools  # noqa: E402
from arcdesk.ai.llm import Message  # noqa: E402
from arcdesk.ai.persona import SYSTEM_PROMPT, machine_brief  # noqa: E402

W = 74


def bar(c: str = "─") -> None:
    print(c * W)


def stage(n, title: str) -> None:
    print(f"\n[{n}] {title}")
    print("    " + "·" * (W - 4))


def say(label: str, value: str) -> None:
    print(f"    {label:<20} {value}")


def clip(s: str, n: int = 118) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


class ScriptedClient:
    """A stand-in for the real model: same interface, recorded answers."""

    provider = "scripted"
    base_url = "scripted://local"
    model = "recording-1"

    def __init__(self, rounds: list[Message]):
        self.rounds = rounds
        self.seen: list[list[Message]] = []

    def describe(self) -> str:
        return "Scripted recording (no network)"

    def chat(self, messages: list[Message], schema: list[dict] | None = None) -> Message:
        self.seen.append([Message(m.role, m.content, m.tool_calls, m.tool_call_id)
                          for m in messages])
        i = len(self.seen) - 1
        return self.rounds[i] if i < len(self.rounds) else Message("assistant", "Done.")

    def forget(self) -> None:
        self.seen.clear()


def call(name: str, args: dict, cid: str = "") -> dict:
    return {"id": cid or f"call_{name}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def run_agent(phrase: str, script: list[Message]) -> tuple[list[str], list[str], float]:
    """Run the REAL agent loop with the scripted model; collect what it emitted."""
    replies: list[str] = []
    used: list[str] = []
    cfg = {"ai": {"enabled": True, "provider": "lite", "voice": False}, "cost": {}}
    ag = agent_mod.Agent(cfg)
    ag.brain, ag.client = "llm", ScriptedClient(script)
    ag.reply.connect(lambda t: replies.append(t))
    ag.tool_used.connect(lambda n, a, r: used.append(f"{n}({a}) → {clip(r, 90)}"))
    t0 = time.time()
    ag._history.append(Message(role="user", content=phrase))
    ag._run_llm()
    return replies, used, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phrase", nargs="*")
    ap.add_argument("--confirm", metavar="PHRASE",
                    help='run a destructive request, e.g. "shut down the pc"')
    args = ap.parse_args()
    QApplication.instance() or QApplication([sys.argv[0]])

    phrase = " ".join(args.phrase).strip() or "how much ram am i using, and draw me a cat"
    if args.confirm:
        return confirm_demo(args.confirm)

    print(f'ARC DESK · thinking trace · "{phrase}"')
    bar("=")

    schema = tools.schemas()
    raw = json.dumps(schema)
    cfg = config.load()
    ai = cfg.get("ai", {}) or {}

    # ------------------------------------------------------------- 1
    stage(1, "WHAT THE MODEL IS GIVEN (agent._run_llm)")
    say("system", f"{len(SYSTEM_PROMPT)} chars — persona + honesty rules")
    say("context", clip(machine_brief(), 100))
    say("history", f"last {agent_mod.MAX_HISTORY} messages kept, trimmed on every turn")
    say("tools", f"{len(schema)} schemas · {len(raw) // 1024} KB JSON · tool_choice=auto")
    say("temperature", "0.3 — steady, not creative; you want the same action every time")
    say("provider", f"{ai.get('provider', 'lite')} (not contacted in this trace)")
    print("    " + "-" * 68)
    print("    The model sees tools, not code. It cannot touch the machine — it can only")
    print("    ask for a tool by name with JSON arguments. Every guard lives outside it.")

    # ------------------------------------------------------------- 2
    stage(2, "ROUND 1 — THE MODEL DECIDES")
    script = [
        Message("assistant", "", [call("system_report", {}, "c1"), call("draw", {"subject": "cat"}, "c2")]),
        Message("assistant", "You are using about 180 MB, and the cat is on your screen — "
                             "saved to Pictures, ArcArt."),
    ]
    replies, used, secs = run_agent(phrase, script)
    say("finish_reason", "tool_calls — it chose two tools, it did not answer yet")
    say("call 1", 'system_report({})')
    say("call 2", 'draw({"subject": "cat"})')
    print("    " + "-" * 68)
    print("    Why two calls in one round: the model batches independent work. It does not")
    print("    need the RAM number to draw a cat, so waiting between them would only add")
    print("    latency. Dependent steps cannot batch — those become a second round.")

    # ------------------------------------------------------------- 3
    stage(3, "EXECUTION — agent._execute() → tools.call()")
    for line in used:
        say("ran", clip(line, 110))
    say("permission gate", "spec.confirm is False for both, so no dialog appeared")
    say("result cap", "each result is truncated to 1500 chars before it goes back")
    say("why cap", "a tool that dumps a 2 MB file would otherwise blow the context window")

    # ------------------------------------------------------------- 4
    stage(4, "ROUND 2 — THE MODEL READS WHAT ACTUALLY HAPPENED")
    say("input now", "system + your sentence + its tool calls + 2 tool results")
    say("finish_reason", "stop — no more tools, so this is the answer")
    say("answer", "")
    print("        " + (replies[0] if replies else "(none)"))
    say("loop budget", f"max {agent_mod.MAX_TOOL_ROUNDS} tool rounds, "
                      f"{secs * 1000:.0f} ms of real agent time in this trace")
    print("    " + "-" * 68)
    print("    This second pass is the part people miss. The model is not asked to")
    print("    remember what it tried; the tool result is appended as a message, so")
    print("    round 2 reasons over ground truth instead of its own guess.")

    # ------------------------------------------------------------- 5
    stage(5, "OUTPUT — ONE ANSWER, FOUR PLACES (window._on_reply)")
    say("console", "add_arc(text) — the transcript line you can scroll back through")
    say("reactor", "state SPEAKING for 2.6 s, rings animate, then back to IDLE")
    say("magic screen", "status strip takes text[:70].upper()")
    say("voice", "self.voice.speak(text) — SAPI on Windows, only if ai.voice is on")
    say("palette", "same text via _palette_reply — the floating bar mirrors the console")
    say("tool log", "add_tool(name, args, result) so you can audit what ran")
    print("    " + "-" * 68)
    print("    Same string everywhere, so what you hear, what you see and what is in the")
    print("    log can never disagree. Speech is the last step and never blocks the UI.")

    # ------------------------------------------------------------- 6
    stage(6, "WHEN THE SAME WORDS GO THROUGH LITE INSTEAD")
    lite_phrase = "system status"
    spoken, calls = lite.respond(lite_phrase)
    say("input", repr(lite_phrase))
    say("decided", f"{len(calls)} tool call(s), no model consulted")
    for c in calls:
        f = c["function"]
        say("tool", f'{f["name"]}({f["arguments"]})')
        out = tools.call(f["name"], json.loads(f["arguments"] or "{}"))
        say("  →", clip(lite.summarise_tool_result(f["name"], out, {}), 110))
    say("cost", "0 bytes of network, 0 model RAM, ~1 ms")
    print("    " + "-" * 68)
    print("    Lite and Brain share one tool registry, so a phrase that works offline")
    print("    keeps working when you plug a model in — only the understanding improves.")

    print()
    bar("=")
    print("Think: prompt → tool calls → ground-truth results → answer → four outputs.")
    return 0


def confirm_demo(phrase: str) -> int:
    print(f'ARC DESK · permission gate · "{phrase}"')
    bar("=")
    print("\n[1] the model asks for a destructive tool — exactly as it would in round 1")
    spec_names = [n for n, s in tools.TOOLS.items() if getattr(s, "confirm", False)]
    say("tools behind a gate", str(len(spec_names)) + " of " + str(len(tools.TOOLS)))
    say("examples", ", ".join(spec_names[:8]))

    print("\n[2] agent._execute() stops before running it")
    say("sequence", "needs_confirm.emit(name, args) → GUI builds a QMessageBox")
    say("default button", "No — an accidental Enter denies, it does not shut down")
    say("wait", "45 s for your click; no answer inside 45 s counts as denied")
    say("denied path", 'returns "user denied permission" to the model as the tool result')
    print("    " + "-" * 68)
    print("    The model is told the truth: it was denied. It cannot retry its way around")
    print("    you, because every retry comes back through the same gate.")

    print("\n[3] what the user sees")
    say("dialog", '"ARC wants to run:  power"  + the exact JSON arguments')
    say("console", "allowed · power   /   denied · power")
    say("log", "logs/arcdesk.log records the tool name and the decision")
    print()
    bar("=")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
