"""The GitHub package catalogue — every open-source project Arc Desk can drive.

This module is DATA ONLY: no imports of any third-party package, no network, no
side effects. It answers one question honestly: *which open-source projects on
GitHub can do each job in Arc Desk, and which of them are already on this PC?*

Rules the catalogue obeys (they are enforced by tests/test_catalog.py):

 1. Every row points at a real GitHub repository (or is marked ``closed``).
 2. Every row lists its licence, including the awkward ones (AGPL, GPL).
 3. Nothing here costs money. A project that needs a paid API key to work at
    all is not "free" and is not allowed in as a backend.
 4. We never vendor the code. Arc Desk talks to these over a port, a CLI or a
    Python import — "use, never copy" (see CREDITS.md).

Detection kinds, kept deliberately dumb so a scan costs milliseconds:
    port:11434      something is listening there
    exe:ollama      command resolvable on PATH
    pip:vosk        importable in the running Python
    file:<rel>      a known file/folder exists in the user profile
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Roles map 1:1 to the pieces of a JARVIS.
ROLES: dict[str, str] = {
    "brain": "Think — turn words into plans and answers",
    "ears": "Listen — turn speech into text",
    "mouth": "Speak — turn text into voice",
    "wake": "Always-on wake word, before anything else runs",
    "tools": "Act — extra tools, usually over MCP",
    "glue": "Support — runtime libraries the rest stand on",
    "see": "See — read screens, photos and documents",
    "recall": "Recall — remember your files. Retrieval and search",
    "flow": "Flow — repeatable automation, not one-off commands",
    "ship": "Ship — build, install and update the app itself",
}


@dataclass(frozen=True)
class Package:
    key: str
    name: str
    repo: str                      # GitHub path, or "" when closed source
    licence: str
    role: str
    job: str                       # what it actually does for ARC
    detect: str = ""               # see module docstring
    install: str = ""              # one line the user can paste
    arc_uses: bool = False         # wired into Arc Desk today?
    note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repo}" if self.repo else ""

    @property
    def is_open_source(self) -> bool:
        return bool(self.repo)


CATALOG: tuple[Package, ...] = (
    # ------------------------------------------------------------------ brain
    Package("ollama", "Ollama", "ollama/ollama", "MIT", "brain",
            "Runs GGUF models, exposes an OpenAI-compatible API on :11434",
            "port:11434", "winget install Ollama.Ollama", True,
            "The recommended free brain. One command, CPU or GPU.",
            ("gguf", "cpu", "recommended")),
    Package("llamacpp", "llama.cpp (llama-server)", "ggml-org/llama.cpp", "MIT", "brain",
            "The C/C++ engine everything else wraps; server on :8080",
            "port:8080", "winget install llama.cpp", True,
            "Most hardware coverage of any engine: CPU, CUDA, Vulkan, ROCm, SYCL.",
            ("gguf", "cpu", "engine")),
    Package("llamafile", "llamafile", "Mozilla-Ocho/llamafile", "Apache-2.0", "brain",
            "One executable = engine + weights; runs straight off the disk",
            "exe:llamafile", "download one .llamafile from the releases page", False,
            "Zero-install path: a single file, no Python, no service. Its built-in "
            "server is llama.cpp's, so Arc Desk reaches it on :8080.",
            ("gguf", "portable", "zero-install")),
    Package("localai", "LocalAI", "mudler/LocalAI", "MIT", "brain",
            "Drop-in OpenAI replacement with the widest API compatibility",
            "port:8080", "docker run -p 8080:8080 localai/localai", True,
            "Good when some other tool insists on a real OpenAI-shaped API.",
            ("gguf", "api")),
    Package("vllm", "vLLM", "vllm-project/vllm", "Apache-2.0", "brain",
            "High-throughput serving with PagedAttention, :8000",
            "port:8000", "pip install vllm", True,
            "Needs a real GPU. Overkill for one desktop user; included because "
            "people have it.",
            ("gpu", "server")),
    Package("sglang", "SGLang", "sgl-project/sglang", "Apache-2.0", "brain",
            "Fast structured generation and serving, :30000",
            "port:30000", "pip install 'sglang[all]'", True,
            "Best-in-class when you want the model to emit guaranteed JSON.",
            ("gpu", "server")),
    Package("jan", "Jan", "janhq/jan", "AGPL-3.0", "brain",
            "Desktop app that runs a local OpenAI-compatible server on :1337",
            "port:1337", "download from jan.ai", True,
            "AGPL applies to Jan itself; we only send HTTP requests to it.",
            ("gguf", "gui")),
    Package("gpt4all", "GPT4All", "nomic-ai/gpt4all", "MIT", "brain",
            "Local chat app with built-in document search, server on :4891",
            "port:4891", "download from nomic.ai", True,
            "Simplest way to chat with your own files offline.",
            ("gguf", "gui", "rag")),
    Package("koboldcpp", "KoboldCpp", "LostRuins/koboldcpp", "AGPL-3.0", "brain",
            "Single-file GGUF runner, server on :5001",
            "port:5001", "download koboldcpp.exe from releases", True,
            "Very forgiving on old GPUs and low-RAM laptops.",
            ("gguf", "portable")),
    Package("textgen", "text-generation-webui", "oobabooga/text-generation-webui",
            "AGPL-3.0", "brain",
            "Swiss-army UI over many loaders, API on :5000",
            "port:5000", "git clone + start_windows.bat", True,
            "Huge option surface; heavier than Ollama for the same result.",
            ("gui", "power-user")),
    Package("aphrodite", "Aphrodite Engine", "aphrodite-engine/aphrodite-engine",
            "AGPL-3.0", "brain",
            "vLLM fork tuned for single-GPU consumer cards, :2242",
            "port:2242", "pip install aphrodite-engine", True,
            "Better than vLLM on one gaming GPU.",
            ("gpu", "server")),
    Package("lmstudio", "LM Studio", "", "freeware (closed source)", "brain",
            "Polished GUI with a local OpenAI server on :1234",
            "port:1234", "download from lmstudio.ai", True,
            "NOT open source. Listed only so detection is honest: many people "
            "already run it. Free to use, no account needed for local mode.",
            ("gguf", "gui", "closed")),

    # ------------------------------------------------------------------- ears
    Package("vosk", "Vosk", "alphacep/vosk-api", "Apache-2.0", "ears",
            "Streaming STT with partial results, 20+ languages, 50 MB models",
            "pip:vosk", "pip install vosk", True,
            "What Arc Desk ships with: tiny, offline, no key, partial results for "
            "the wake word.",
            ("stt", "streaming", "light")),
    Package("sherpa", "sherpa-onnx", "k2-fsa/sherpa-onnx", "Apache-2.0", "ears",
            "STT + TTS + VAD + keyword spotting in one ONNX runtime, fully offline",
            "pip:sherpa_onnx", "pip install sherpa-onnx", False,
            "The strongest single upgrade available: it can replace Vosk, the TTS "
            "and the wake word at once, with no PyTorch.",
            ("stt", "tts", "vad", "kws")),
    Package("whispercpp", "whisper.cpp", "ggml-org/whisper.cpp", "MIT", "ears",
            "Whisper in C/C++, CPU or GPU, no Python needed",
            "exe:whisper-cli", "winget install whisper.cpp", False,
            "Much better accuracy than Vosk on accents and noise; needs a bigger "
            "model and more RAM.",
            ("stt", "accurate")),
    Package("fasterwhisper", "faster-whisper", "SYSTRAN/faster-whisper", "MIT", "ears",
            "Whisper re-implemented on CTranslate2, several times faster",
            "pip:faster_whisper", "pip install faster-whisper", False,
            "Best accuracy-per-second on CPU if you can spare ~1 GB.",
            ("stt", "accurate")),
    Package("whisper", "OpenAI Whisper", "openai/whisper", "MIT", "ears",
            "The reference model and trainer (weights are MIT)",
            "pip:whisper", "pip install openai-whisper", False,
            "The model is open. The *API* at openai.com is not — that stays blocked.",
            ("stt", "model")),

    # ------------------------------------------------------------------ mouth
    Package("piper", "Piper", "rhasspy/piper", "MIT", "mouth",
            "Fast neural TTS, one ONNX voice per language, runs on a Pi",
            "pip:piper", "pip install piper-tts", False,
            "The natural next step after Windows SAPI: far more human, still offline.",
            ("tts", "neural")),
    Package("kokoro", "Kokoro", "hexgrad/kokoro", "Apache-2.0", "mouth",
            "82M-parameter TTS that sounds close to paid cloud voices",
            "pip:kokoro", "pip install kokoro", False,
            "Best free voice quality in 2026 for the size. ~350 MB of runtime.",
            ("tts", "neural", "quality")),
    Package("espeak", "eSpeak NG", "espeak-ng/espeak-ng", "GPL-3.0", "mouth",
            "Robotic but indestructible formant synthesiser",
            "exe:espeak-ng", "winget install eSpeak-NG", False,
            "Fallback of last resort: 2 MB, works on anything, sounds like 1985.",
            ("tts", "light", "fallback")),
    Package("coqui", "Coqui TTS (XTTS)", "coqui-ai/TTS", "MPL-2.0", "mouth",
            "Voice cloning and many voices",
            "pip:TTS", "pip install TTS", False,
            "Unmaintained upstream since 2024. Great results, abandoned project — "
            "use Kokoro unless you specifically need cloning.",
            ("tts", "cloning", "unmaintained")),

    # ------------------------------------------------------------------- wake
    Package("openwakeword", "openWakeWord", "dscripka/openWakeWord", "Apache-2.0", "wake",
            "Open wake-word models, 200 KB ONNX, runs on CPU in real time",
            "pip:openwakeword", "pip install openwakeword", False,
            "You can train your own phrase instead of borrowing 'hey jarvis'. "
            "Ships a pre-trained hey_jarvis model.",
            ("kws", "custom")),
    Package("sherpa-kws", "sherpa-onnx KWS", "k2-fsa/sherpa-onnx", "Apache-2.0", "wake",
            "Streaming keyword spotting from the same sherpa-onnx runtime",
            "pip:sherpa_onnx", "pip install sherpa-onnx", False,
            "One dependency for ears + wake word, instead of two.",
            ("kws",)),
    Package("porcupine", "Picovoice Porcupine", "picovoice/porcupine", "Apache-2.0 code, "
            "free tier needs an AccessKey", "wake",
            "Very accurate wake word with a hosted console",
            "", "pip install pvporcupine", False,
            "Excluded as a default: the library is open but usage needs a Picovoice "
            "account and their free tier has terms. openWakeWord does the same job "
            "with no account, so that is what Arc Desk points at.",
            ("kws", "account-required", "not-default")),

    # ------------------------------------------------------------------ tools
    Package("mcp-servers", "MCP reference servers", "modelcontextprotocol/servers",
            "MIT", "tools",
            "Filesystem, Fetch, Time, Memory, Git, Sequential Thinking",
            "exe:npx", "npx -y @modelcontextprotocol/server-filesystem .", True,
            "Arc Desk already speaks MCP: paste any command in Settings and its "
            "tools appear as mcp__<server>__<tool>.",
            ("mcp", "tools")),
    Package("mcp-sdk", "MCP Python SDK", "modelcontextprotocol/python-sdk", "MIT", "tools",
            "The protocol implementation Arc Desk's own MCP client follows",
            "pip:mcp", "pip install mcp", False,
            "Our client is ~300 lines of stdlib JSON-RPC, written from the spec, so "
            "the app has no runtime dependency on this. Listed for reference.",
            ("mcp", "spec")),
    Package("playwright-mcp", "Playwright MCP", "microsoft/playwright-mcp", "Apache-2.0",
            "tools",
            "Drives a real browser: click, type, screenshot, read the DOM",
            "exe:npx", "npx -y @playwright/mcp", False,
            "Gives JARVIS hands on the web without any paid API.",
            ("mcp", "browser")),
    Package("github-mcp", "GitHub MCP Server", "github/github-mcp-server", "MIT", "tools",
            "Issues, pull requests, code search, Actions",
            "exe:docker", "docker run -i --rm ghcr.io/github/github-mcp-server", False,
            "Needs a GitHub token — free, but an account. Off by default.",
            ("mcp", "github")),

    # ------------------------------------------------------------------- glue
    Package("onnxruntime", "ONNX Runtime", "microsoft/onnxruntime", "MIT", "glue",
            "Runs the small speech models without PyTorch",
            "pip:onnxruntime", "pip install onnxruntime", False,
            "The reason sherpa / openWakeWord start in milliseconds.",
            ("runtime",)),
    Package("sounddevice", "python-sounddevice", "spatialaudio/python-sounddevice", "MIT",
            "glue", "Microphone capture through PortAudio",
            "pip:sounddevice", "pip install sounddevice", True,
            "What the wake daemon records with. One import, no visible window.",
            ("audio",)),
    Package("silero-vad", "Silero VAD", "snakers4/silero-vad", "MIT", "glue",
            "Voice activity detection, 1 MB ONNX",
            "pip:silero_vad", "pip install silero-vad", False,
            "Stops the app listening to silence, so the CPU idles instead of working.",
            ("vad", "audio")),
    Package("pywinauto", "pywinauto", "pywinauto/pywinauto", "BSD-3-Clause", "glue",
            "Windows UI automation for apps with no CLI",
            "pip:pywinauto", "pip install pywinauto", False,
            "Optional reach: lets JARVIS press buttons in old Windows programs. Not "
            "bundled — it touches the desktop, and the guard treats that carefully.",
            ("windows", "uia")),
    Package("pyinstaller", "PyInstaller", "pyinstaller/pyinstaller", "GPL-2.0 with "
            "bootloader exception", "glue",
            "Turns run.py into ArcDesk.exe",
            "pip:PyInstaller", "pip install pyinstaller", True,
            "The exception is what makes shipping a closed or open app from GPL "
            "build tooling legal.",
            ("build",)),

    # ------------------------------------------------------- brain (more)
    Package("exo", "exo", "exo-explore/exo", "Apache-2.0", "brain",
            "Runs one model across several machines on your desk, :52415",
            "port:52415", "git clone + python3 run.py", False,
            "Two old laptops together beat one new one. Only worth it if you "
            "already own the hardware.", ()),
    Package("llamacpp-python", "llama-cpp-python server", "abetlen/llama-cpp-python",
            "MIT", "brain",
            "llama.cpp with Python bindings and a built-in OpenAI server, :8000",
            "pip:llama_cpp", "pip install 'llama-cpp-python[server]'", False,
            "Use this when you want the engine inside your own Python script "
            "instead of a separate service.", ()),
    Package("node-llamacpp", "node-llama-cpp", "withcatai/node-llama-cpp", "MIT", "brain",
            "The same engine for JavaScript, with automatic GPU offload",
            "", "npm install node-llama-cpp", False,
            "Relevant only for the Electron-style side projects around JARVIS.", ()),
    Package("trtllm", "TensorRT-LLM", "NVIDIA/TensorRT-LLM", "Apache-2.0", "brain",
            "NVIDIA's fastest inference, compiled per GPU model",
            "", "docker pull nvcr.io/nvidia/tensorrt-llm", False,
            "Highest speed on NVIDIA hardware, and the most setup pain. Needs a "
            "build step that is measured in hours, not minutes.", ()),
    Package("lmdeploy", "LMDeploy", "InternLM/lmdeploy", "Apache-2.0", "brain",
            "Efficient serving with strong quantisation support, :23333",
            "port:23333", "pip install lmdeploy", False,
            "Good middle ground: nearly vLLM speed with easier Windows install.", ()),
    Package("transformers", "Hugging Face Transformers", "huggingface/transformers",
            "Apache-2.0", "brain",
            "Loads almost any open model into plain Python",
            "pip:transformers", "pip install transformers", False,
            "The library every other project wraps. Slowest of the group because "
            "it is general, but the widest model coverage.", ()),
    Package("unsloth", "Unsloth", "unslothai/unsloth", "Apache-2.0", "brain",
            "Trains and fine-tunes small models on one consumer GPU",
            "pip:unsloth", "pip install unsloth", False,
            "The free path to teaching a model your own writing style. Needs a "
            "GPU; nothing here is required for normal use.", ()),
    Package("minicpm", "MiniCPM", "OpenBMB/MiniCPM", "Apache-2.0", "brain",
            "Small strong models, some with vision, tuned for phones and laptops",
            "", "download GGUF from the releases page", False,
            "Fits in 2-3 GB of RAM and still answers sensibly — the best fit for "
            "a low-spec laptop.", ()),
    Package("qwen", "Qwen", "QwenLM/Qwen3", "Apache-2.0", "brain",
            "The strongest small open models for tool calling",
            "", "ollama pull qwen3:4b", False,
            "Best free choice for reliable tool calls at 3-4B. Apache-2.0 weights, "
            "no usage policy attached.", ()),

    # -------------------------------------------------------- ears (more)
    Package("wyoming", "Wyoming", "rhasspy/wyoming", "Apache-2.0", "ears",
            "A tiny JSON protocol so STT, TTS and wake word become swappable services",
            "", "pip install wyoming", False,
            "Interesting if you ever want ears and mouth in separate processes; "
            "Arc Desk keeps them in-process today to save RAM.", ()),
    Package("pyannote", "pyannote.audio", "pyannote/pyannote-audio", "MIT", "ears",
            "Speaker diarisation — who spoke when",
            "pip:pyannote.audio", "pip install pyannote.audio", False,
            "Useful for meeting recordings, not for a single user talking to JARVIS.", ()),
    Package("nemo", "NVIDIA NeMo", "NVIDIA/NeMo", "Apache-2.0", "ears",
            "Research-grade speech and language toolkit",
            "pip:nemo_toolkit", "pip install nemo_toolkit[asr]", False,
            "Heavy (PyTorch first) but the accuracy ceiling is high.", ()),
    Package("deepspeech", "Mozilla DeepSpeech", "mozilla/DeepSpeech", "MPL-2.0", "ears",
            "The project that proved offline STT was practical",
            "", "", False,
            "Archived upstream since 2021. Listed because old tutorials still "
            "point at it — use Vosk or sherpa-onnx instead.", ("archived",)),

    # ------------------------------------------------------- mouth (more)
    Package("openvoice", "OpenVoice", "myshell-ai/OpenVoice", "MIT", "mouth",
            "Clones a tone of voice from a few seconds of audio",
            "", "git clone + pip install -e .", False,
            "Could give JARVIS a deeper, more 'manly' voice than a stock TTS. Clone "
            "only your own voice — not a stranger's.", ("tts", "cloning")),
    Package("rvc", "RVC voice conversion", "RVC-Project/Retrieval-based-Voice-Conversion-WebUI",
            "MIT", "mouth",
            "Realtime voice-to-voice conversion on CPU or GPU",
            "", "git clone + run the web UI", False,
            "Post-processes any TTS into a chosen timbre. Same rule: your voice, "
            "your consent.", ("tts", "cloning")),

    # --------------------------------------------------------------- see
    Package("tesseract", "Tesseract OCR", "tesseract-ocr/tesseract", "Apache-2.0", "see",
            "Classic OCR engine; reads text out of any window or photo",
            "exe:tesseract", "winget install UB-Mannheim.TesseractOCR", True,
            "Arc Desk already reads the screen with it. Small, offline, 100+ "
            "languages.", ("ocr", "screen")),
    Package("paddleocr", "PaddleOCR", "PaddlePaddle/PaddleOCR", "Apache-2.0", "see",
            "Much better accuracy than Tesseract on real-world photos",
            "pip:paddleocr", "pip install paddleocr", False,
            "Handles rotated, blurry and mixed-language text far better. Heavier "
            "install (~500 MB with Paddle).", ("ocr", "accurate")),
    Package("easyocr", "EasyOCR", "JaidedAI/EasyOCR", "Apache-2.0", "see",
            "PyTorch OCR in 80+ languages with a two-line API",
            "pip:easyocr", "pip install easyocr", False,
            "Easiest to start with; pulls PyTorch in.", ("ocr",)),
    Package("markitdown", "MarkItDown", "microsoft/markitdown", "MIT", "see",
            "Turns PDF, Word, Excel, PPT and images into clean Markdown",
            "pip:markitdown", "pip install markitdown", False,
            "Would let JARVIS read any document with one function instead of the "
            "per-format readers it has now. Strong candidate.", ("documents",)),
    Package("docling", "Docling", "docling-project/docling", "MIT", "see",
            "Layout-aware document parsing: tables, columns, reading order",
            "pip:docling", "pip install docling", False,
            "Best free extractor for messy PDFs with tables. Slower than a text "
            "reader, so only for files that need it.", ("documents", "tables")),
    Package("omniparser", "OmniParser", "microsoft/OmniParser", "MIT", "see",
            "Turns a screenshot into a labelled list of clickable UI elements",
            "", "git clone + pip install -r requirements.txt", False,
            "This is how 'click the Save button' becomes reliable without a "
            "vision API. The most interesting row in this group.", ("ui", "vision")),
    Package("clip", "CLIP", "openai/CLIP", "MIT", "see",
            "Matches images to text — search your photos by description",
            "pip:clip", "pip install git+https://github.com/openai/CLIP", False,
            "Enables 'find the photo with the red bike' over a local folder. "
            "Weights are MIT.", ("vision", "search")),
    Package("yolo", "Ultralytics YOLO", "ultralytics/ultralytics", "AGPL-3.0", "see",
            "Real-time object detection",
            "pip:ultralytics", "pip install ultralytics", False,
            "AGPL: fine to run, awkward if you ever ship a modified version. Not "
            "needed for JARVIS's current jobs.", ("vision",)),
    Package("qwen-vl", "Qwen2.5-VL", "QwenLM/Qwen2.5-VL", "Apache-2.0", "see",
            "An open vision model that can describe and reason about a screenshot",
            "", "ollama pull qwen2.5vl:3b", False,
            "A real 'look at my screen and explain it' brain, fully offline, if "
            "you have ~4 GB spare.", ("vision", "vlm")),

    # ------------------------------------------------------------ recall
    Package("chroma", "Chroma", "chroma-core/chroma", "Apache-2.0", "recall",
            "Embedded vector database — the easy default for local RAG",
            "pip:chromadb", "pip install chromadb", False,
            "One folder, no server, no account. What JARVIS would use first for "
            "'ask my documents'.", ("rag", "embedded")),
    Package("qdrant", "Qdrant", "qdrant/qdrant", "Apache-2.0", "recall",
            "Fast vector search server in Rust, :6333",
            "port:6333", "docker run -p 6333:6333 qdrant/qdrant", False,
            "Better than Chroma past roughly a million chunks; overkill below it.", ()),
    Package("faiss", "FAISS", "facebookresearch/faiss", "MIT", "recall",
            "The original similarity-search library",
            "pip:faiss", "pip install faiss-cpu", False,
            "Fastest raw index, no frills: you store the text yourself.", ()),
    Package("lancedb", "LanceDB", "lancedb/lancedb", "Apache-2.0", "recall",
            "Columnar vector store that also keeps your metadata",
            "pip:lancedb", "pip install lancedb", False,
            "Good when search results need filters like date or file type.", ()),
    Package("txtai", "txtai", "neuml/txtai", "Apache-2.0", "recall",
            "All-in-one embeddings database with keyword + vector hybrid search",
            "pip:txtai", "pip install txtai", False,
            "Hybrid search in one dependency — closest match to what Arc Desk's "
            "own file index does, but semantic.", ("rag", "hybrid")),
    Package("unstructured", "Unstructured", "Unstructured-IO/unstructured",
            "Apache-2.0", "recall",
            "Chops PDFs, emails and HTML into clean chunks for indexing",
            "pip:unstructured", "pip install unstructured", False,
            "The boring half of RAG that decides whether the answers are any good.", ()),

    # -------------------------------------------------------------- flow
    Package("autohotkey", "AutoHotkey", "AutoHotkey/AutoHotkey", "GPL-2.0", "flow",
            "Windows hotkeys and macros in a scripting language",
            "exe:autohotkey", "winget install AutoHotkey.AutoHotkey", False,
            "JARVIS already sends keystrokes itself; AHK is for macros you want to "
            "run with JARVIS closed.", ()),
    Package("autokey", "AutoKey", "autokey/autokey", "GPL-3.0", "flow",
            "The same idea on Linux and X11 desktops",
            "exe:autokey", "pip install autokey", False,
            "Kept for the small number of users running Arc Desk on Linux.", ()),
    Package("prefect", "Prefect", "PrefectHQ/prefect", "Apache-2.0", "flow",
            "Schedules and retries multi-step jobs",
            "pip:prefect", "pip install prefect", False,
            "If a nightly 'clean my downloads, back up notes' job grows past a "
            "few steps, this is the free scheduler for it.", ()),
    Package("browser-use", "Browser Use", "browser-use/browser-use", "MIT", "flow",
            "Lets a model drive a real browser step by step",
            "pip:browser_use", "pip install browser-use", False,
            "Similar ground to Playwright MCP, but in-process. Needs a capable "
            "local model to be useful.", ("browser",)),
    Package("skyvern", "Skyvern", "Skyvern-AI/skyvern", "AGPL-3.0", "flow",
            "Browser workflows that survive layout changes",
            "", "docker compose up", False,
            "Aimed at form-filling at scale; heavy for one desktop.", ()),

    # ------------------------------------------------------------- tools
    Package("serena", "Serena", "oraios/serena", "MIT", "tools",
            "MCP server that gives a model real code intelligence: symbols, refs",
            "exe:uvx", "uvx --from git+https://github.com/oraios/serena serena", False,
            "The best free way to make a small model useful on a real codebase.", ("mcp", "code")),
    Package("playwright-py", "Playwright for Python", "microsoft/playwright-python",
            "Apache-2.0", "tools",
            "Scripted browser control with no model needed",
            "pip:playwright", "pip install playwright", False,
            "Deterministic: JARVIS records the steps once, replays them forever.", ("browser",)),
    Package("puppeteer", "Puppeteer", "puppeteer/puppeteer", "Apache-2.0", "tools",
            "The JavaScript equivalent, driving headless Chrome",
            "exe:npx", "npx puppeteer browsers install chrome", False,
            "Only if the browser automation lives on the JS side.", ("browser",)),
    Package("llm-cli", "llm", "simonw/llm", "Apache-2.0", "tools",
            "A command line for models, with plugins for local servers",
            "exe:llm", "pip install llm", False,
            "Handy for testing what a local model can actually do before wiring "
            "it into JARVIS.", ("cli",)),
    Package("awesome-mcp", "awesome-mcp-servers", "punkpeye/awesome-mcp-servers",
            "MIT", "tools",
            "A hand-maintained index of MCP servers you can paste into Settings",
            "", "", False,
            "Read it before writing a new integration — someone usually has one.",
            ("mcp", "list")),

    # -------------------------------------------------------------- glue
    Package("psutil", "psutil", "giampaolo/psutil", "BSD-3-Clause", "glue",
            "CPU, memory, disk, battery and process stats on every OS",
            "pip:psutil", "pip install psutil", True,
            "Every real number on the hologram comes from here. If it is missing, "
            "Arc Desk says so instead of inventing figures.", ("stats",)),
    Package("pywin32", "pywin32", "mhammond/pywin32", "PSF-2.0", "glue",
            "Windows APIs: volume, brightness, clipboard, window handles",
            "pip:win32api", "pip install pywin32", True,
            "How JARVIS mutes, dims and locks without any external tool.", ("windows",)),
    Package("mss", "mss", "BoboTiG/python-mss", "MIT", "glue",
            "Very fast cross-platform screenshots",
            "pip:mss", "pip install mss", False,
            "About 10x faster than a naive grab — relevant if screen reading ever "
            "needs to run per frame.", ("screen",)),
    Package("opencv", "OpenCV (Python)", "opencv/opencv-python", "Apache-2.0", "glue",
            "Image resizing, template matching, thresholding",
            "pip:cv2", "pip install opencv-python", False,
            "Would replace the hand-written numpy work in the vision module with "
            "tested code.", ("vision",)),
    Package("pillow", "Pillow", "python-pillow/Pillow", "MIT-CMU", "glue",
            "Image load, save and convert for every format",
            "pip:PIL", "pip install pillow", True,
            "Behind every screenshot resize and OCR pre-process Arc Desk does.", ("image",)),
    Package("ffmpeg", "FFmpeg", "FFmpeg/FFmpeg", "LGPL-2.1-or-later", "glue",
            "The video and audio converter everything else calls",
            "exe:ffmpeg", "winget install Gyan.FFmpeg", True,
            "All video and audio work is handed to ffmpeg as a separate process, "
            "so none of it loads inside the Qt app. That is why RAM stays flat.",
            ("media", "external")),
    Package("watchdog", "watchdog", "gorakhargosh/watchdog", "Apache-2.0", "glue",
            "Notifies you when files change, instead of polling",
            "pip:watchdog", "pip install watchdog", False,
            "Would let the file index stay warm for free — currently it rescans "
            "on a timer.", ("files",)),
    Package("rapidfuzz", "RapidFuzz", "rapidfuzz/RapidFuzz", "MIT", "glue",
            "C++ fuzzy string matching with honest scores",
            "pip:rapidfuzz", "pip install rapidfuzz", False,
            "The command palette and file search both do fuzzy matching by hand; "
            "this would be faster and better at typos.", ("fuzzy",)),
    Package("websockets", "websockets", "python-websockets/websockets", "BSD-3-Clause",
            "glue", "Clean async WebSocket client for streaming model output",
            "pip:websockets", "pip install websockets", False,
            "Arc Desk streams with raw sockets today to stay dependency-free; "
            "this is the alternative.", ("net",)),
    Package("httpx", "HTTPX", "encode/httpx", "BSD-3-Clause", "glue",
            "Modern HTTP client with timeouts done right",
            "pip:httpx", "pip install httpx", False,
            "Same story: urllib is enough for local ports, httpx is nicer if that "
            "ever changes.", ("net",)),

    # -------------------------------------------------------------- ship
    Package("nuitka", "Nuitka", "Nuitka/Nuitka", "Apache-2.0", "ship",
            "Compiles Python to C — smaller, faster start than freezing",
            "pip:nuitka", "pip install nuitka", False,
            "Alternative to PyInstaller if antivirus keeps flagging the PyInstaller "
            "bundle. Both are free.", ("build",)),
    Package("inno", "Inno Setup", "jrsoftware/issrc", "Inno Setup licence (free, "
            "source available)", "ship",
            "Makes a normal Windows installer and uninstaller",
            "exe:iscc", "winget install JRSoftware.InnoSetup", False,
            "The polite way to ship Arc Desk: a real uninstaller in Add/Remove "
            "Programs, which is what uninstall.bat apologises for not having.",
            ("installer",)),
    Package("uv", "uv", "astral-sh/uv", "MIT / Apache-2.0", "ship",
            "Installs Python and dependencies in seconds",
            "", "winget install astral-sh.uv", False,
            "Makes the 'install JARVIS from source' path one command instead of five.",
            ("packaging",)),
)

BY_KEY: dict[str, Package] = {p.key: p for p in CATALOG}

# Projects deliberately left out of the stack. Kept in the file (not hidden) so
# the reasoning is reviewable instead of being an invisible omission.
REFUSED: tuple[tuple[str, str], ...] = (
    ("xtekky/gpt4free",
     "Routes your prompts through reverse-engineered endpoints to get paid models "
     "for free. That is evading someone's billing, not open source, and it breaks "
     "their terms. Arc Desk's whole point is that nothing is ever charged — not "
     "that someone else is charged instead."),
    ("Any 'unlimited API key' / cracked-key repo",
     "Same failure: stolen credentials. Also a security hole, since the traffic "
     "goes through whoever shipped it."),
    ("Anthropic/OpenAI/Gemini SDKs as the default brain",
     "Not refused as software — refused as a default. They are free to install and "
     "cost money the moment they answer, so the cost guard blocks them until you "
     "explicitly raise the limit."),
)


def by_role(role: str) -> tuple[Package, ...]:
    return tuple(p for p in CATALOG if p.role == role)


def wired() -> tuple[Package, ...]:
    """Packages Arc Desk actually talks to today."""
    return tuple(p for p in CATALOG if p.arc_uses)


def summary() -> dict[str, int]:
    counts: dict[str, int] = {r: 0 for r in ROLES}
    for p in CATALOG:
        counts[p.role] = counts.get(p.role, 0) + 1
    counts["total"] = len(CATALOG)
    counts["wired"] = len(wired())
    counts["open_source"] = sum(1 for p in CATALOG if p.is_open_source)
    return counts


def check() -> list[str]:
    """Self-consistency: returns a list of problems (empty means the data is sane)."""
    problems: list[str] = []
    seen: set[str] = set()
    for p in CATALOG:
        if p.key in seen:
            problems.append(f"duplicate key: {p.key}")
        seen.add(p.key)
        if p.role not in ROLES:
            problems.append(f"{p.key}: unknown role {p.role!r}")
        if not p.job:
            problems.append(f"{p.key}: no job description")
        if p.is_open_source and "/" not in p.repo:
            problems.append(f"{p.key}: repo {p.repo!r} is not owner/name")
        if p.detect:
            kind = p.detect.split(":", 1)[0]
            if kind not in {"port", "exe", "pip", "file"}:
                problems.append(f"{p.key}: bad detect kind {kind!r}")
        lowered = (p.name + p.note).lower()
        for word in ("subscription", "per month", "usd", "$"):
            if word in lowered:
                problems.append(f"{p.key}: money wording {word!r} — this stack is ₹0")
    return problems
