"""LLM providers — one OpenAI-compatible client covers all of them.

Why this shape:
  * Ollama exposes /v1/chat/completions, Groq/Gemini/OpenRouter/OpenAI all speak
    the same schema. So one client, five providers, no SDK dependency.
  * Built on urllib: zero new packages, zero import cost at startup.
  * Nothing here runs at import time; the client is created only when the user
    actually asks the assistant something.

Cost note (₹0 path): Groq and Gemini both have free tiers. Ollama is fully local
and free but loads 2-3 GB of RAM in its OWN process, which is why we never load
a model inside Arc Desk.
"""
from __future__ import annotations

import json
import re
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

PROVIDERS = {
    "groq": {
        "label": "Groq (free tier)",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "env": "GROQ_API_KEY",
        "needs_key": True,
        "note": "Fast and free. Get a key at console.groq.com",
    },
    "gemini": {
        "label": "Google Gemini (free tier)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "env": "GEMINI_API_KEY",
        "needs_key": True,
        "note": "Free tier, good tool calling. aistudio.google.com",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "env": "OPENAI_API_KEY",
        "needs_key": True,
        "note": "Paid, most reliable tool calling.",
    },
    "ollama": {
        "label": "Ollama (local, offline)",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "llama3.2:3b",
        "env": None,
        "needs_key": False,
        "note": "Runs on your own laptop. ~2.5 GB RAM in Ollama's process, not in Arc Desk.",
    },
    "custom": {
        "label": "Custom OpenAI-compatible",
        "base_url": "",
        "model": "",
        "env": "ARC_API_KEY",
        "needs_key": True,
        "note": "LM Studio, vLLM, OpenRouter, anything /v1 compatible.",
    },
}


@dataclass
class Message:
    role: str
    content: str = ""
    tool_calls: list = field(default_factory=list)
    tool_call_id: str = ""
    # token accounting, when the provider reports it (llama.cpp, Ollama, Groq do).
    # Kept out of as_dict() on purpose: it is diagnostics, not conversation.
    usage: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d: dict = {"role": self.role}
        if self.content:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


_TOOL_BLOCK = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.S)
_FUNC_BLOCK = re.compile(r"<function\s*=\s*([A-Za-z0-9_.\-]+)\s*>\s*(.*?)\s*</function>", re.S)
_NAKED_CALL = re.compile(r'^\s*(\{.*"name"\s*:.*\})\s*$', re.S)


def _loads_loose(body: str):
    """json.loads, but tolerant of the doubled braces Qwen2.5 actually emits.

    Observed on a real run: the model writes `<tool_call>{{"name": "time",
    "arguments": {}}}</tool_call>` — jinja's tojson escaped once too many on the
    way out. Strict JSON then fails on a call that is perfectly obvious to a
    human, which is the worst kind of failure: correct intent, dropped action.
    """
    for candidate in (body, body.replace("{{", "{").replace("}}", "}"),
                      body.strip().strip("{}")):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _as_call(name: str, args, index: int) -> dict:
    if not isinstance(args, str):
        args = json.dumps(args, ensure_ascii=False)
    return {"id": f"textcall_{index}", "type": "function",
            "function": {"name": name, "arguments": args}}


def parse_text_tool_calls(content: str) -> tuple[list, str]:
    """Recover tool calls that a local model wrote as text instead of JSON.

    Measured on a real llama.cpp server: Qwen2.5 answers
    `<tool_call>{"name": "time", "arguments": {}}</tool_call>` in the content
    field, and llama-cpp-python passes that through verbatim. Any assistant that
    only reads `tool_calls` looks broken there — it repeats the XML at the user
    like a parrot. Three shapes are common enough to be worth handling:

        <tool_call>{"name": "time", "arguments": {}}</tool_call>      Qwen, Hermes
        <function=open_app>{"app": "notepad"}</function>             some fine-tunes
        {"name": "time", "arguments": {}}                             bare, whole reply

    Returns (calls, remaining_text). Unparseable blocks are left alone.
    """
    calls: list = []
    text = content or ""

    def _take(match, name_from_group: bool) -> None:
        nonlocal text
        name = match.group(1).strip() if name_from_group else ""
        body = (match.group(2) if name_from_group else match.group(1)).strip()
        obj = _loads_loose(body)
        if obj is None:
            return
        if isinstance(obj, dict):
            if not name:
                name = str(obj.get("name") or obj.get("function") or "").strip()
                args = obj.get("arguments", obj.get("parameters", obj.get("args", {})))
            else:
                # <function=name>{"app": "notepad"}</function> — the body IS the args
                args = obj.get("arguments", obj)
        else:
            return
        if not name:
            return
        calls.append(_as_call(name, args, len(calls) + 1))
        text = text.replace(match.group(0), " ")

    for match in list(_FUNC_BLOCK.finditer(text)):
        _take(match, True)
    for match in list(_TOOL_BLOCK.finditer(text)):
        _take(match, False)
    if not calls:
        naked = _NAKED_CALL.match(text)
        if naked:
            _take(naked, False)
    return calls, " ".join(text.split())


def _merge_tool_deltas(deltas: list[dict]) -> list[dict]:
    """Streaming tool calls arrive in pieces: index, partial name, partial JSON.

    Providers agree on this much: each delta has an `index`, the first one carries
    the id and the function name, and the arguments accumulate as a string. Getting
    the concat wrong produces a JSON error at exactly the moment the user is
    watching, so it gets its own tested merge.
    """
    merged: dict[int, dict] = {}
    for delta in deltas:
        for piece in delta or []:
            idx = int(piece.get("index", 0) or 0)
            slot = merged.setdefault(idx, {"id": "", "type": "function",
                                           "function": {"name": "", "arguments": ""}})
            if piece.get("id"):
                slot["id"] = piece["id"]
            fn = piece.get("function") or {}
            if fn.get("name"):
                slot["function"]["name"] += fn["name"]
            if fn.get("arguments"):
                slot["function"]["arguments"] += fn["arguments"]
    out = [merged[i] for i in sorted(merged)]
    for i, call in enumerate(out):
        if not call["id"]:
            call["id"] = f"streamcall_{i + 1}"
        if not call["function"]["arguments"].strip():
            call["function"]["arguments"] = "{}"
    return out


class LLMError(RuntimeError):
    pass


class ToolCallFormatError(LLMError):
    """The model asked for a tool but produced unparseable JSON.

    Small local models do this — a 0.5B model given 26 tool schemas will
    occasionally emit a truncated argument object. llama.cpp rejects it with an
    HTTP 500 instead of passing it on, so it has to be caught here and handled as
    "the brain fumbled", not as "the provider is down".
    """


class LLMClient:
    #: Some servers drop the tool schema when `stream: true` is set (measured:
    #: llama.cpp's llama-server answers from memory and calls nothing). The agent
    #: reads this flag and asks for its planning round without streaming there.
    tool_stream_ok: bool = True

    def __init__(self, provider: str, base_url: str, model: str,
                 api_key: str = "", timeout: float = 60.0) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    # -- construction from app config ------------------------------------
    @classmethod
    def from_config(cls, ai_cfg: dict, cost_cfg: dict | None = None) -> "LLMClient":
        name = (ai_cfg.get("provider") or "auto").strip()
        if name == "auto":
            name = detect_provider(ai_cfg)
        spec = PROVIDERS.get(name) or PROVIDERS["custom"]
        key = (ai_cfg.get("api_key") or "").strip()
        if not key and spec["env"]:
            key = (os.getenv(spec["env"]) or "").strip()
        base = (ai_cfg.get("base_url") or "").strip() or spec["base_url"]
        model = (ai_cfg.get("model") or "").strip() or spec["model"]

        # a detected local backend supplies its own URL + first loaded model
        if name not in PROVIDERS:
            local = detect_local_backend()
            if local and local[0] == name:
                base, model = local[1], (model or local[2])
                if not base:
                    base = ""

        # ---- cost guard: never spend money because of a stale config ----
        try:
            from . import cost as _cost
            cfg_cost = cost_cfg or {}
            if cfg_cost.get("enabled", True):
                max_class = str(cfg_cost.get("max_class") or _cost.MAX_DEFAULT)
                cls_ = _cost.classify(name, base)
                if not _cost.allowed(cls_, max_class):
                    raise LLMError(_cost.explain_refusal(name, max_class))
        except LLMError:
            raise
        except Exception:
            pass    # a broken guard import must not brick the app

        return cls(name, base, model, key)

    def describe(self) -> str:
        label = PROVIDERS.get(self.provider, {}).get("label", self.provider)
        return f"{label} · {self.model}"

    # -- chat ------------------------------------------------------------
    def supports_tool_stream(self) -> bool:
        """True when this server honours `tools` and `stream: true` together."""
        name = (self.provider or "").lower()
        if name in {"llama.cpp", "llamacpp", "llama-server", "llamaserver"}:
            return False
        return self.tool_stream_ok

    def supports_stream(self) -> bool:
        """Ollama, llama.cpp, LM Studio, vLLM and OpenAI all stream. Cheap to ask."""
        return str(getattr(self, "base_url", "")).startswith(("http://", "https://"))

    def chat_stream(self, messages: list[Message], tools: list[dict] | None = None,
                    on_delta=None) -> Message:
        """Same call, but the answer arrives in pieces.

        `on_delta(text)` fires for every content token, so the window can start
        speaking the first sentence while the rest is still being generated. Falls
        back to a normal (blocking) call when the server ignores `stream: true` —
        a silent fallback is better than an empty answer.
        """
        if not self.base_url:
            raise LLMError("no base URL configured")
        payload: dict = {
            "model": self.model,
            "messages": [m.as_dict() for m in messages],
            "temperature": 0.3,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Accept": "text/event-stream",
                     **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})},
            method="POST",
        )
        content: list[str] = []
        tool_pieces: list[dict] = []
        usage: dict = {}
        saw_event = False
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "event-stream" not in ctype:
                    # server does not stream: read the whole body and treat it normally
                    data = json.loads(resp.read().decode("utf-8"))
                    choice = data["choices"][0]["message"]
                    text = (choice.get("content") or "").strip()
                    calls = choice.get("tool_calls") or []
                    if not calls and text:
                        calls, text = parse_text_tool_calls(text)
                    if text and on_delta:
                        on_delta(text)
                    return Message(role="assistant", content=text, tool_calls=calls,
                                   usage=data.get("usage") or {})
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        event = json.loads(chunk)
                    except Exception:
                        continue
                    saw_event = True
                    if event.get("usage"):
                        usage.update(event["usage"])
                    for choice in event.get("choices") or []:
                        delta = choice.get("delta") or {}
                        text = delta.get("content") or ""
                        if text:
                            content.append(text)
                            if on_delta:
                                on_delta(text)
                        if delta.get("tool_calls"):
                            tool_pieces.append(delta["tool_calls"])
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            low = body.lower()
            if "tool call" in low or "tool_calls" in low or "parse error" in low:
                raise ToolCallFormatError("the model produced a malformed tool call") from exc
            raise LLMError(f"HTTP {exc.code}: {body or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"cannot reach provider ({exc.reason})") from exc
        except Exception as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        text = "".join(content).strip()
        calls = _merge_tool_deltas(tool_pieces)
        if not calls and text:
            calls, text = parse_text_tool_calls(text)
        if not saw_event and not text and not calls:
            return self.chat(messages, tools)
        return Message(role="assistant", content=text, tool_calls=calls, usage=usage)

    def chat(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        if not self.base_url:
            raise LLMError("no base URL configured")
        payload: dict = {
            "model": self.model,
            "messages": [m.as_dict() for m in messages],
            "temperature": 0.3,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            low = body.lower()
            if "tool call" in low or "tool_calls" in low or "parse error" in low:
                raise ToolCallFormatError(
                    "the model produced a malformed tool call") from exc
            raise LLMError(f"HTTP {exc.code}: {body or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"cannot reach provider ({exc.reason})") from exc
        except Exception as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        try:
            choice = data["choices"][0]["message"]
        except Exception as exc:
            raise LLMError("unexpected response shape") from exc

        content = (choice.get("content") or "").strip()
        calls = choice.get("tool_calls") or []
        usage = data.get("usage") or {}
        if not calls and content:
            calls, cleaned = parse_text_tool_calls(content)
            if calls:
                content = cleaned
                usage = {**usage, "recovered_tool_calls": len(calls)}
        return Message(
            role="assistant",
            content=content,
            tool_calls=calls,
            usage=usage,
        )


def detect_local_backend() -> tuple[str, str, str] | None:
    """Return (provider_key, base_url, model) for a running local open-source
    backend, or None. Delegates to arcdesk.ai.backends so there is one list."""
    try:
        from . import backends
        best = backends.best_local()
        if best is None:
            return None
        model = best.models[0] if best.models else ""
        return best.backend.key, best.base_url, model
    except Exception:
        return None


def detect_provider(ai_cfg: dict) -> str:
    """Pick the first brain that is actually usable, cheapest first."""
    forced = (ai_cfg.get("provider") or "auto").strip()
    if forced != "auto":
        return forced

    key = (ai_cfg.get("api_key") or "").strip()
    if key and (ai_cfg.get("base_url") or "").strip():
        return "custom"
    for name in ("groq", "gemini", "openai"):
        spec = PROVIDERS[name]
        if key or os.getenv(spec["env"]):
            return name
    local = detect_local_backend()
    if local is not None:
        return local[0]
    return "lite"


def ollama_alive(timeout: float = 0.6) -> bool:
    """Cheap liveness probe. It is still a socket: call it from a worker.

    "Cheap" was wrong when it was written — a refused connect is fast, but 11434 on a
    machine with a firewall rule or a suspended Docker container is not, and the AI setup
    page called this while it was building itself (`20.png`). Use `uiwork.run`, or
    `ollama_alive_soon()` which never blocks.
    """
    return _ollama_check(timeout)


def _ollama_check(timeout: float = 0.6) -> bool:
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


#: Last answer, and when. `ollama_alive_soon()` is for code that cannot wait.
_ALIVE: dict = {"at": 0.0, "value": False}
_ALIVE_SECONDS = 20.0
_ALIVE_WARMING = None


def ollama_alive_soon(timeout: float = 0.6) -> bool:
    """The last known answer, with a background refresh. Never opens a socket here.

    On a worker (or in a tool) it does the real check, so callers that can afford to wait
    still get the truth.
    """
    import threading
    import time

    if threading.current_thread() is not threading.main_thread():
        value = _ollama_check(timeout)
        _ALIVE.update(at=time.monotonic(), value=value)
        return value
    stale = (time.monotonic() - _ALIVE["at"]) > _ALIVE_SECONDS
    if stale and not (_ALIVE_WARMING is not None and _ALIVE_WARMING.is_alive()):
        def warm() -> None:
            _ALIVE.update(at=time.monotonic(), value=_ollama_check(timeout))

        globals()["_ALIVE_WARMING"] = threading.Thread(target=warm, name="arc-ollama-probe",
                                                       daemon=True)
        _ALIVE_WARMING.start()
    return bool(_ALIVE["value"])
