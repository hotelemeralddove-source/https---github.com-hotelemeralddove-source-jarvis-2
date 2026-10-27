"""The guards around the agent loop — the parts that stop a model misbehaving.

`test_agent_loop.py` proves the happy path works over real HTTP. This file proves
the *limits* work, with a scripted client so there is no server and no network:

  1. a model that never stops asking for tools cannot loop forever (MAX_TOOL_ROUNDS)
  2. a denied confirmation never reaches the tool, and the model is told the truth
  3. an allowed confirmation does run it
  4. a huge tool result is truncated before it goes back to the model
  5. an invented tool name is reported as an error, not executed
  6. a machine fact stated without a tool call is replaced by measured data
  7. a machine fact stated after calling *some* tool is still grounded
  8. a tool call written as text (<tool_call>…</tool_call>) is recovered, not echoed

Run:  QT_QPA_PLATFORM=offscreen python tests/test_agent_guards.py
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk.ai import tools  # noqa: E402
from arcdesk.ai.agent import MAX_TOOL_ROUNDS, Agent  # noqa: E402
from arcdesk.ai.llm import Message  # noqa: E402


class ScriptedClient:
    """Same interface as LLMClient.chat; answers from a list, then repeats the last."""

    provider = "scripted"
    base_url = "scripted://test"

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls = 0
        self.last_messages = []

    def describe(self) -> str:
        return "scripted"

    def chat(self, messages, schema=None):
        self.calls += 1
        self.last_messages = list(messages)
        i = min(self.calls - 1, len(self.rounds) - 1)
        return self.rounds[i]


def tool_call(name: str, args: str = "{}", cid: str = "c1") -> dict:
    return {"id": cid, "type": "function",
            "function": {"name": name, "arguments": args}}


def make_agent(client) -> tuple[Agent, dict]:
    seen = {"replies": [], "tools": [], "confirm": []}
    cfg = {"ai": {"enabled": True, "provider": "lite", "voice": False}, "cost": {}}
    ag = Agent(cfg)
    ag.brain, ag.client = "llm", client
    ag.reply.connect(lambda t: seen["replies"].append(t))
    ag.tool_used.connect(lambda n, a, r: seen["tools"].append((n, a, r)))
    ag.needs_confirm.connect(lambda n, a: seen["confirm"].append((n, a)))
    return ag, seen


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<52} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def main() -> int:
    QApplication.instance() or QApplication([sys.argv[0]])
    ok = True

    # ---------- 1. bounded loop -------------------------------------
    print("1) a tool-hungry model is bounded by MAX_TOOL_ROUNDS")
    client = ScriptedClient([Message("assistant", "", [tool_call("time")])])
    ag, seen = make_agent(client)
    ag._run_llm()
    ok &= check(f"model calls = {MAX_TOOL_ROUNDS + 1}", client.calls, MAX_TOOL_ROUNDS + 1)
    ok &= check("gave up with an explanation, not silence",
                "circles" in (seen["replies"][-1] if seen["replies"] else ""), True)

    # ---------- 2. denial is respected ------------------------------
    print("2) a denied confirmation never reaches the tool")
    ran: list[str] = []
    real_call = tools.call
    def spy(name, args=None):
        ran.append(name)
        return "SHOULD NOT RUN"
    tools.call = spy
    try:
        client = ScriptedClient([
            Message("assistant", "", [tool_call("power", '{"action": "shutdown"}')]),
            Message("assistant", "I did not shut it down."),
        ])
        ag, seen = make_agent(client)
        ag.answer_confirm(False)          # the user clicks No
        ag._run_llm()
        ok &= check("confirmation dialog was requested", len(seen["confirm"]), 1)
        ok &= check("tool never executed", ran, [])
        told = [m.content for m in client.last_messages if m.role == "tool"]
        ok &= check("model was told it was denied", told[-1] if told else "", "user denied permission")
    finally:
        tools.call = real_call

    # ---------- 3. granted confirmation runs it ---------------------
    print("3) an allowed confirmation does run the tool")
    ran.clear()
    tools.call = spy
    try:
        client = ScriptedClient([
            Message("assistant", "", [tool_call("power", '{"action": "shutdown"}')]),
            Message("assistant", "Shutting down."),
        ])
        ag, seen = make_agent(client)
        ag.answer_confirm(True)
        ag._run_llm()
        ok &= check("tool executed once", ran, ["power"])
    finally:
        tools.call = real_call

    # ---------- 4. results are truncated ---------------------------
    print("4) a huge tool result is truncated before it returns to the model")
    client = ScriptedClient([
        Message("assistant", "", [tool_call("time")]),
        Message("assistant", "done"),
    ])
    tools.call = lambda name, args=None: "x" * 4000
    try:
        ag, seen = make_agent(client)
        ag._run_llm()
        told = [m for m in client.last_messages if m.role == "tool"]
        ok &= check("tool message capped at 1500 chars",
                    len(told[-1].content) if told else -1, 1500)
    finally:
        tools.call = real_call

    # ---------- 5. invented tools are refused ----------------------
    print("5) a tool name the model invented is an error, not an execution")
    client = ScriptedClient([
        Message("assistant", "", [tool_call("format_c_drive")]),
        Message("assistant", "That is not something I can do."),
    ])
    ag, seen = make_agent(client)
    ag._run_llm()
    told = [m.content for m in client.last_messages if m.role == "tool"]
    ok &= check("error mentions the unknown tool",
                bool(told) and "unknown tool" in told[-1], True)

    # ---------- 6. hallucinated machine facts are grounded ----------
    print("6) a machine fact with no tool call is replaced by measured data")
    client = ScriptedClient([
        Message("assistant", "The time is 10:00 AM and you are using 0% of your RAM."),
    ])
    ag, seen = make_agent(client)
    ag._run_llm()
    reply = seen["replies"][-1] if seen["replies"] else ""
    ok &= check("fabricated hour is gone", "10:00 AM" in reply, False)
    ok &= check("measured values were used instead", "ram" in reply.lower(), True)
    ok &= check("the user is told why", "I measured that" in reply, True)
    ok &= check("the measuring tools are logged", len(seen["tools"]), 2)

    # ---------- 6b. one unrelated tool call does not license a RAM claim ------
    print("6b) calling `time` does not let it invent the memory figure")
    client = ScriptedClient([
        Message("assistant", "", [tool_call("time")]),
        Message("assistant", "It is 10:00 AM and you are using about 1 GB of RAM."),
    ])
    ag, seen = make_agent(client)
    ag._run_llm()
    reply = seen["replies"][-1] if seen["replies"] else ""
    ok &= check("invented figure replaced", "about 1 GB of RAM" in reply, False)
    ok &= check("measured figure present", "ram" in reply.lower(), True)
    ok &= check("system_report was actually run",
                any(n == "system_report" for n, _, _ in seen["tools"]), True)
    ok &= check("time is not logged twice",
                sum(1 for n, _, _ in seen["tools"] if n == "time"), 1)

    # ---------- 7. ordinary answers are left alone -------------------
    print("7) an answer with no machine claim is passed through untouched")
    client = ScriptedClient([Message("assistant", "I drew a cat for you.")])
    ag, seen = make_agent(client)
    ag._run_llm()
    ok &= check("reply unchanged", seen["replies"][-1], "I drew a cat for you.")

    # ---------- 8. tool calls written as text are recovered ----------
    print("8) a <tool_call> block in the content is a tool call, not prose")
    from arcdesk.ai.llm import parse_text_tool_calls
    calls, left = parse_text_tool_calls('<tool_call>\n{{"name": "time", "arguments": {}}}\n</tool_call>')
    ok &= check("doubled braces parsed", len(calls), 1)
    ok &= check("name recovered", calls[0]["function"]["name"] if calls else "", "time")
    ok &= check("nothing left to say", left, "")
    calls2, _ = parse_text_tool_calls('<function=open_app>{"app": "notepad"}</function>')
    ok &= check("function= form", calls2[0]["function"]["arguments"] if calls2 else "", '{"app": "notepad"}')
    calls3, same = parse_text_tool_calls("The time is 11:50.")
    ok &= check("plain prose untouched", (calls3, same), ([], "The time is 11:50."))

    print("\n" + ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
