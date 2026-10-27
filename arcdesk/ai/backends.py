"""Local / open-source AI backends — detect what is already running on this PC.

Every entry below is a real open-source project on GitHub that exposes an
OpenAI-compatible HTTP API. Arc Desk does not vendor them and does not bundle
their code: it talks to them over localhost, exactly like it talks to Groq.
That means:

  * you install whichever one you like (or none)
  * the model's RAM lives in *their* process, never inside Arc Desk
  * swapping the brain is a URL, not a code change

Detection is a 250 ms TCP connect per port, run once on demand (never on the
startup path), so a missing backend costs nothing.
"""
from __future__ import annotations

import json
import socket
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Backend:
    key: str
    label: str
    repo: str            # GitHub project, for the docs and the UI
    port: int            # default listening port
    path: str            # base path for the OpenAI API
    models_path: str = "/models"
    licence: str = ""

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}{self.path}"


BACKENDS: tuple[Backend, ...] = (
    Backend("ollama", "Ollama", "github.com/ollama/ollama", 11434, "/v1", "/models", "MIT"),
    Backend("llamacpp", "llama.cpp server", "github.com/ggml-org/llama.cpp",
            8080, "/v1", "/models", "MIT"),
    Backend("localai", "LocalAI", "github.com/mudler/LocalAI", 8080, "/v1", "/models", "MIT"),
    Backend("lmstudio", "LM Studio", "lmstudio.ai (closed UI, local server)",
            1234, "/v1", "/models", "freeware"),
    Backend("vllm", "vLLM", "github.com/vllm-project/vllm", 8000, "/v1", "/models", "Apache-2.0"),
    Backend("jan", "Jan", "github.com/janhq/jan", 1337, "/v1", "/models", "AGPL-3.0"),
    Backend("gpt4all", "GPT4All", "github.com/nomic-ai/gpt4all",
            4891, "/v1", "/models", "MIT"),
    Backend("koboldcpp", "KoboldCpp", "github.com/LostRuins/koboldcpp",
            5001, "/v1", "/models", "AGPL-3.0"),
    Backend("textgen", "text-generation-webui", "github.com/oobabooga/text-generation-webui",
            5000, "/v1", "/models", "AGPL-3.0"),
    Backend("sglang", "SGLang", "github.com/sgl-project/sglang", 30000, "/v1", "/models",
            "Apache-2.0"),
    Backend("aphrodite", "Aphrodite Engine", "github.com/aphrodite-engine/aphrodite-engine",
            2242, "/v1", "/models", "AGPL-3.0"),
    # llamafile and LocalAI both serve llama.cpp's API on :8080, which the
    # llamacpp entry above already detects — no duplicate row, first match wins.
)


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _models(base_url: str, timeout: float = 1.5) -> list[str]:
    try:
        req = urllib.request.Request(base_url.rstrip("/") + "/models",
                                     headers={"User-Agent": "ArcDesk"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("data") if isinstance(data, dict) else None
        return [str(m.get("id")) for m in (items or []) if m.get("id")]
    except Exception:
        return []


@dataclass
class Detected:
    backend: Backend
    base_url: str
    models: list[str]

    def describe(self) -> str:
        if self.models:
            return f"{self.backend.label} · {self.models[0]}"
        return f"{self.backend.label} (no model loaded)"


def probe(timeout: float = 0.25) -> list[Detected]:
    """Return every backend that answers on its port. Cheap; call it on demand."""
    found: list[Detected] = []
    seen_ports: set[tuple[int, str]] = set()
    for b in BACKENDS:
        key = (b.port, b.path)
        if key in seen_ports:
            continue
        if not _port_open(b.port, timeout=timeout):
            continue
        url = b.base_url()
        models = _models(url)
        seen_ports.add(key)
        found.append(Detected(b, url, models))
    return found


def best_local() -> Detected | None:
    """Prefer a backend that actually has a model loaded."""
    found = probe()
    for d in found:
        if d.models:
            return d
    return found[0] if found else None


def quick_health(url: str, timeout: float = 1.2) -> tuple[bool, str]:
    """Used by the settings dialog's 'test' button."""
    try:
        models = _models(url, timeout=timeout)
        if models:
            return True, "online · " + ", ".join(models[:3])
        return True, "online · you still need to load a model"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


INSTALL_HINTS = {
    "ollama": "curl -fsSL https://ollama.com/install.sh | sh   (or the Windows installer)\n"
              "then:  ollama pull llama3.2:3b   →  runs on 127.0.0.1:11434",
    "llamacpp": "github.com/ggml-org/llama.cpp releases → llama-server.exe\n"
                "llama-server -m model.gguf --port 8080  →  gives /v1 automatically",
    "localai": "github.com/mudler/LocalAI  ·  docker run -p 8080:8080 localai/localai\n"
               "supports gguf + whisper + diffusion, all local",
    "lmstudio": "lmstudio.ai → Local Server tab → start on port 1234",
    "vllm": "pip install vllm  ·  vllm serve <model> --port 8000   (GPU recommended)",
    "jan": "github.com/janhq/jan  ·  Jan → Settings → Local API server → port 1337",
    "gpt4all": "nomic.ai/gpt4all → Settings → Enable API server (port 4891)",
    "koboldcpp": "github.com/LostRuins/koboldcpp releases → koboldcpp.exe --port 5001",
    "textgen": "github.com/oobabooga/text-generation-webui → run with --api --port 5000",
    "sglang": "pip install 'sglang[all]'  ·  python -m sglang.launch_server --port 30000",
    "aphrodite": "pip install aphrodite-engine  ·  aphrodite run <model> --port 2242",
    "llamafile": "download one .llamafile from github.com/Mozilla-Ocho/llamafile/releases\n"
                 "./<model>.llamafile --server --port 8080   (no install at all)",
}
