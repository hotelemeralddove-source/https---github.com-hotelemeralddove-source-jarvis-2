"""The agent loop — think, call tools, read results, answer.

Runs on its own thread so a 6-second model response can never freeze the reactor
animation or the clock. Everything it touches that belongs to the GUI is emitted
as a signal and executed on the main thread.

Flow per request:
    user text -> [system + context + history] -> model
      -> if tool calls: (confirm if destructive) -> run -> append result -> model again
      -> final spoken text

Bounded on purpose: max 4 tool rounds, max 12 history messages. A runaway loop
would eat the CPU budget we promised to protect.
"""
from __future__ import annotations

import json
import re
import threading

from PySide6.QtCore import QObject, Signal

from .. import activity as _activity
from .. import profile
from . import lite, select, tools
from .. import lang as langs
from .llm import LLMClient, LLMError, Message, ToolCallFormatError
from .persona import machine_brief, system_prompt

MAX_TOOL_ROUNDS = 4
MAX_HISTORY = 12


def text_for_language(history: list) -> str:
    """The most recent thing the user said — that decides the reply language."""
    for msg in reversed(history):
        if getattr(msg, "role", "") == "user" and getattr(msg, "content", ""):
            return msg.content
    return ""

# Words that mean "this sentence claims something about THIS machine". A model that
# answers one of these without calling a tool is guessing — and small local models
# guess confidently: a 1.5B model told us "the time is 10:00 AM" and "0% of RAM"
# without touching a tool. So the answer gets replaced by measured data.
FACT_WORDS = re.compile(
    r"\b(ram|cpu|memory|disk|battery|temperature|o'?clock|"
    r"\d{1,3}\s?%|\d{1,2}:\d{2}\s?(?:am|pm)|\d{1,2}\s?(?:am|pm)|gigabyte|gb|mb)\b",
    re.I,
)


def claims_machine_facts(text: str) -> bool:
    return bool(FACT_WORDS.search(text or ""))


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n+")
MIN_SPEAK = 24          # a 3-word fragment sounds like a glitch, so keep buffering


def split_ready(buffer: str, min_len: int = MIN_SPEAK) -> tuple[str, str]:
    """Take the finished part of a streaming answer, keep the unfinished tail.

    "Nifty is 22,687. It is" → ("Nifty is 22,687.", "It is"). Splitting on the last
    boundary means the model can be half-way through a sentence and the first one
    is already being spoken, which is where the perceived speed comes from.
    """
    text = buffer or ""
    cut = -1
    for match in _SENTENCE_END.finditer(text):
        if match.start() >= min_len:
            cut = match.end()
            break
    if cut > 0:
        return text[:cut].strip(), text[cut:]
    if len(text) > 240:                       # no punctuation, but long enough to say
        cut = text.rfind(" ", 0, 200)
        if cut > 0:
            return text[:cut].strip(), text[cut:]
        if len(text) > 240 and " " not in text:
            return text, ""                    # one giant token: say it, do not stall
    return "", text


class Agent(QObject):
    # emitted from the worker thread; Qt queues them onto the GUI thread
    thinking = Signal(bool)
    reply = Signal(str)                      # final assistant text
    tool_used = Signal(str, str, str)        # name, args-json, result
    error = Signal(str)
    needs_confirm = Signal(str, str)         # tool name, args-json
    learned = Signal(str)                    # ARC learned a durable fact about you
    speak_partial = Signal(str)              # a sentence ready to be spoken now
    speak_end = Signal()                     # nothing more to say this turn
    step_started = Signal(str)               # "tool: open_app" — now, on screen
    step_finished = Signal(str, float)       # same label, and how long it took
    brain_changed = Signal(str)

    def __init__(self, cfg: dict, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._history: list[Message] = []
        self._pending = ""             # the follow-up said while an answer was running
        self._busy = threading.Lock()
        self._confirm_event = threading.Event()
        self._confirm_answer = False
        self.client: LLMClient | None = None
        self.blocked_reason = ""
        self.brain = "lite"
        self.context_fn = lambda: machine_brief()

    # -- public ----------------------------------------------------------
    def describe(self) -> str:
        from . import cost as _cost
        if self.brain == "lite" or self.client is None:
            base = "JARVIS LITE · offline · FREE"
            return base + ("  ·  paid provider blocked" if self.blocked_reason else "")
        label = self.client.describe()
        cls_ = _cost.classify(self.client.provider, self.client.base_url)
        out = f"{label} · {_cost.LABELS[cls_]}"
        if self.blocked_reason:
            out += "  ·  paid provider blocked"
        return out

    def reset(self) -> None:
        self._history.clear()
        self.reply.emit("Context cleared.")

    def answer_confirm(self, accepted: bool) -> None:
        self._confirm_answer = bool(accepted)
        self._confirm_event.set()

    def ask(self, text: str) -> None:
        """Take a request. If one is already running, KEEP the new one instead of dropping it.

        A conversation means two people talking, not one interrupting: while the answer to
        "what is my battery" is still being written, the follow-up "and the CPU?" used to
        be thrown away with "Still working on the previous request…". The person then
        heard their question ignored and repeated it — "repeated ah pesitae iruku, confuse
        aaguthu". Now the newest request is remembered and started the moment the current
        one finishes; only the newest, so nothing piles up.
        """
        text = (text or "").strip()
        if not text:
            return
        if self._busy.locked():
            self._pending = text
            self.error.emit("I am still on the last one — I will take this as soon as it "
                            "finishes, so you do not have to say it twice.")
            return
        threading.Thread(target=self._run, args=(text,), daemon=True,
                         name="arc-agent").start()

    # -- internals -------------------------------------------------------
    def _run(self, text: str) -> None:
        act = _activity.activity()
        self._last_request = text          # the companion ack quotes this
        with self._busy:
            self.thinking.emit(True)
            act.begin(text)
            try:
                self._resolve_brain()
                # "my name is Arun" becomes memory, not a message the model must re-read
                try:
                    fact = profile.learn(text)
                    if fact:
                        self.learned.emit(fact)
                except Exception:
                    pass
                self._history.append(Message(role="user", content=text))
                self._trim()
                if self.brain == "lite":
                    self._run_lite(text)
                elif self._fast_path(text):
                    self._run_lite(text)          # Lite already knew exactly what to do
                else:
                    # the model is the slowest thing in the app, so it gets a step of
                    # its own on screen: "thinking" with a clock is not the same
                    # experience as a blank window (the user's complaint)
                    started_at = _activity.time.monotonic()
                    self.step_started.emit("thinking · the model is reading it")
                    self._run_llm()
                    self.step_finished.emit("thinking · the model is reading it",
                                            _activity.time.monotonic() - started_at)
            except ToolCallFormatError as exc:
                # the brain fumbled a tool call. Do not lose the request: try it
                # offline through Lite, and say plainly what happened.
                self.error.emit(f"{exc}")
                if self.brain == "llm":
                    handled = self._run_lite(text)
                    if not handled:
                        self.reply.emit(
                            "My model garbled that one, so I did not do anything. "
                            "Ask me again, or say it a simpler way.")
            except LLMError as exc:
                # a cost refusal or a dead provider must fall back, not dead-end
                self.error.emit(f"{exc}")
                if self.brain != "lite":
                    self.brain, self.client = "lite", None
                    self.brain_changed.emit(self.describe())
                self.reply.emit("I could not reach my brain just now. "
                                "Lite mode still works if you need a quick command.")
            except Exception as exc:
                self.error.emit(f"{type(exc).__name__}: {exc}")
            finally:
                try:
                    self.speak_end.emit()
                except Exception:
                    pass
                act.finish(ok=not act.cancelled(),
                           why="" if not act.cancelled() else "you stopped it")
                self.thinking.emit(False)
                # hand over to the follow-up that arrived while this one was running
                nxt, self._pending = self._pending, ""
                if nxt:
                    threading.Thread(target=self._run, args=(nxt,), daemon=True,
                                     name="arc-agent").start()

    def _resolve_brain(self) -> None:
        ai = self.cfg.get("ai", {})
        if not ai.get("enabled", True):
            if self.brain != "lite":
                self.brain = "lite"
                self.brain_changed.emit(self.describe())
            return
        self.blocked_reason = ""
        try:
            client = LLMClient.from_config(ai, self.cfg.get("cost", {}))
        except Exception as exc:
            client = None
            self.blocked_reason = str(exc)
        if client is None or client.provider == "lite" or not client.base_url:
            self.brain, self.client = "lite", None
        else:
            self.brain, self.client = "llm", client
        self.brain_changed.emit(self.describe())

    def _fast_path(self, text: str) -> bool:
        """Did the rule matcher already understand this, with a tool to call?

        Measured reason this exists: a 0.5B model scored 0/8 on "what is 18% of
        4500" and "nifty price" — it chatted instead of calling the tool, and once
        invented a Nifty price. `knows.py` gets those right in microseconds. So the
        model is asked only when the cheap path is not sure, which is both faster
        and more correct. Configurable: `ai.fast_path: false` turns it off.
        """
        if not self.cfg.get("ai", {}).get("fast_path", True):
            return False
        try:
            _spoken, calls = lite.respond(text)
        except Exception:
            return False
        return bool(calls)

    def _on_delta(self, chunk: str) -> None:
        """A streaming token arrived: speak each sentence as soon as it is whole."""
        self._buf += chunk
        while True:
            piece, rest = split_ready(self._buf)
            if not piece:
                break
            self._buf = rest
            self._spoken = True
            self.speak_partial.emit(piece + " ")

    def _routed_schema(self, text: str, schema: list[dict], k: int) -> list[dict]:
        """Keep the tools this sentence could plausibly need; keep list_tools.

        MCP tools are scored too — they arrive as schemas, not Tool objects — so a
        connected GitHub server does not quietly become unreachable.
        """
        from types import SimpleNamespace
        candidates = dict(tools.TOOLS)
        for spec in schema:
            fn = spec.get("function", {})
            name = fn.get("name", "")
            if name and name not in candidates:
                candidates[name] = SimpleNamespace(name=name,
                                                   description=fn.get("description", ""))
        picked = {t.name for t in select.shortlist(text, candidates, k=k)}
        self.route = sorted(picked)
        return [spec for spec in schema if spec["function"]["name"] in picked]

    # -- lite path -------------------------------------------------------
    def _run_lite(self, text: str) -> bool:
        """Answer offline. Returns True if a tool actually ran."""
        spoken, calls = lite.respond(text)
        results: list[str] = []
        for call in calls:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"] or "{}")
            out = self._execute(name, args)
            results.append(lite.summarise_tool_result(name, out, args))
        final = "Stopped." if _activity.activity().cancelled() else \
            (spoken or " ".join(results) or "Done.")
        self.speak_partial.emit(final)
        self.reply.emit(final)
        return bool(calls)

    # -- llm path --------------------------------------------------------
    def _run_llm(self) -> None:
        assert self.client is not None
        # mirror the language the user actually spoke — Tamil, Tanglish, Hindi, English
        said = text_for_language(self._history)
        _code, _style = langs.mirror(said)
        self.language = _code
        known = profile.summary()
        msgs = [Message(role="system",
                        content=system_prompt(self.cfg) + "\n\n" + _style + "\n\n"
                        + (known + "\n\n" if known else "")
                        + (self.context_fn() or ""))]
        msgs.extend(self._history[-MAX_HISTORY:])
        self._called: list[tuple[str, dict]] = []
        ai0 = self.cfg.get("ai", {})
        streaming = bool(ai0.get("stream", True)) and hasattr(self.client, "chat_stream")
        self._buf = ""
        self._spoken = False
        # a small local model drowns in 63 schemas — measured: the whole catalogue
        # is ~3 500 tokens of JSON, which alone overflows a 2 048-token context.
        # So route: score the tools against the sentence and send the best few.
        ai = self.cfg.get("ai", {})
        schema = tools.schemas(core_only=bool(ai.get("core_tools")))
        self.route: list[str] = [s["function"]["name"] for s in schema]
        if str(ai.get("tool_routing", "auto")) != "all" and len(schema) > 12:
            schema = self._routed_schema(said, schema, int(ai.get("tool_shortlist", 8)))

        # Measured on llama.cpp's server: when `stream=true`, the tool schema is
        # silently ignored and the model answers from memory instead of calling a
        # tool. So round 0 (the planning round, where tool calls are decided) is a
        # normal request, and only the wrap-up rounds stream. Servers that do
        # support both (vLLM, Ollama) can be opted in with `ai.stream_tools`.
        stream_tools = bool(ai.get("stream_tools",
                                   self.client.supports_tool_stream()
                                   if hasattr(self.client, "supports_tool_stream") else True))
        for _round in range(MAX_TOOL_ROUNDS + 1):
            use_stream = streaming and (stream_tools or _round > 0)
            if use_stream:
                self._buf = ""
                answer = self.client.chat_stream(msgs, schema, on_delta=self._on_delta)
            else:
                answer = self.client.chat(msgs, schema)
            msgs.append(answer)
            self._history.append(answer)

            if not answer.tool_calls:
                text = answer.content or "I have nothing to add."
                # speak whatever the stream had not yet handed over
                tail = (self._buf or "").strip()
                if tail:
                    self.speak_partial.emit(tail)
                    self._buf = ""
                if not self._spoken and not tail:
                    self.speak_partial.emit(text)
                # Grounding on what was actually checked, not on whether any tool ran.
                # Seen for real: a 0.5B model called `time`, then added "you are using
                # about 1 GB of RAM" — a number it invented. `system_report` was never
                # called, so that sentence is a guess and must not be delivered as fact.
                checked = {name for name, _ in self._called}
                if claims_machine_facts(text) and "system_report" not in checked:
                    text = self._grounded_truth()
                self.reply.emit(text)
                return

            self._buf = ""                    # narration before a tool call is not the answer
            for call in answer.tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}
                self._called.append((name, args))
                result = self._execute(name, args)
                tool_msg = Message(role="tool", content=result[:1500],
                                   tool_call_id=call.get("id", ""))
                msgs.append(tool_msg)
                self._history.append(tool_msg)

        self.reply.emit("I kept going in circles on that one. Try breaking it into "
                        "smaller steps.")

    def _grounded_truth(self) -> str:
        """The model stated a machine fact without checking. Check it here.

        Costs two cheap local tool calls (~5 ms) and turns a hallucination into
        measured values. The user is told plainly which answer to trust.
        """
        parts: list[str] = []
        already = {name for name, _ in getattr(self, "_called", [])}
        for name, args in (("time", {}), ("system_report", {})):
            try:
                out = tools.call(name, args)
                if name not in already:          # do not log the same call twice
                    self.tool_used.emit(name, json.dumps(args), out)
                parts.append(str(out).strip())
            except Exception:
                continue
        if not parts:
            return ("I did not check that properly, so I will not guess. "
                    "Ask me again and I will use a tool.")
        facts = " ".join(" ".join(p.split()).rstrip(".") + "." for p in parts if p.strip())
        if len(facts) > 320:
            facts = facts[:319].rsplit(" ", 1)[0] + "…"
        facts = facts[:1].upper() + facts[1:]
        return (f"{facts} I measured that on this machine. The model's own numbers "
                f"were not checked, so I did not repeat them.")

    # -- shared tool execution with confirmation --------------------------
    def _execute(self, name: str, args: dict) -> str:
        act = _activity.activity()
        if act.cancelled():
            return "stopped before running (you pressed Stop)"
        spec = tools.TOOLS.get(name)
        if spec is None:
            return f"ERROR: unknown tool '{name}'"
        act.step(f"tool: {name}")
        self.step_started.emit(f"tool: {name}")
        began = _activity.time.monotonic()
        if spec.confirm:
            self.needs_confirm.emit(name, json.dumps(args))
            granted = self._confirm_event.wait(timeout=45)
            self._confirm_event.clear()
            if not granted or not self._confirm_answer:
                out = "user denied permission"
                self.tool_used.emit(name, json.dumps(args), out)
                return out
        self.thinking.emit(True)
        started = _activity.time.monotonic()
        try:
            out = tools.call(name, args)
        except Exception as exc:                       # a tool must never kill the turn
            act.note(f"{type(exc).__name__}")
            out = f"ERROR: {type(exc).__name__}: {exc}"
        took = _activity.time.monotonic() - started
        if took >= 1.5:
            # a genuinely slow tool is where "is it working?" gets asked — name it
            act.note(f"slow {took:.1f} s")
        self.tool_used.emit(name, json.dumps(args), out)
        self.step_finished.emit(f"tool: {name}", _activity.time.monotonic() - began)
        if act.cancelled():
            return out + "\n(you stopped the request after this ran)"
        return out

    def _trim(self) -> None:
        if len(self._history) > MAX_HISTORY:
            del self._history[:-MAX_HISTORY]
