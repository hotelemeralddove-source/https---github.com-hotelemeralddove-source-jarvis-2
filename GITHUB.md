# The GitHub stack — every open-source package ARC can use

**86 packages. 85 open source, 1 freeware (labelled). 0 of them cost money.
20 are already wired into Arc Desk.**

This is the answer to *"get the alternatives from GitHub"*. Two halves: the table of
projects, and the scanner that proves which ones are on **your** PC right now.

```bat
python tools\github_scan.py            :: what is installed here
python tools\github_scan.py --all      :: the whole catalogue
python tools\github_scan.py --plan     :: paste-able commands for what is missing
python tools\github_scan.py --json     :: machine readable
python tools\github_scan.py --md GITHUB.md   :: regenerate this file
```

The catalogue is data, not code: `arcdesk/ai/catalog.py` imports nothing, opens no
socket and writes nothing. `tests/test_catalog.py` fails the build if a row gains a
price, a broken repo path, or a detector that does not exist.

Inside the app, ask ARC: **"what packages can read a PDF?"** or **"scan my GitHub
stack"** — the same catalogue answers, from the same file.

Legend: ⭐ = the one to pick if you have no opinion · ★ = Arc Desk drives it today.


## Brain — 21 projects  
*Think — turn words into plans and answers*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **Ollama** ⭐ ★ | `ollama/ollama` | MIT | Runs GGUF models, exposes an OpenAI-compatible API on :11434. The recommended free brain. One command, CPU or GPU. |
| **llama.cpp (llama-server)** ⭐ ★ | `ggml-org/llama.cpp` | MIT | The C/C++ engine everything else wraps; server on :8080. Most hardware coverage of any engine: CPU, CUDA, Vulkan, ROCm, SYCL. |
| **llamafile** | `Mozilla-Ocho/llamafile` | Apache-2.0 | One executable = engine + weights; runs straight off the disk. Zero-install path: a single file, no Python, no service. Its built-in server is llama.cpp's, so Arc Desk reaches it on :8080. |
| **LocalAI** ★ | `mudler/LocalAI` | MIT | Drop-in OpenAI replacement with the widest API compatibility. Good when some other tool insists on a real OpenAI-shaped API. |
| **vLLM** ★ | `vllm-project/vllm` | Apache-2.0 | High-throughput serving with PagedAttention, :8000. Needs a real GPU. Overkill for one desktop user; included because people have it. |
| **SGLang** ★ | `sgl-project/sglang` | Apache-2.0 | Fast structured generation and serving, :30000. Best-in-class when you want the model to emit guaranteed JSON. |
| **Jan** ★ | `janhq/jan` | AGPL-3.0 | Desktop app that runs a local OpenAI-compatible server on :1337. AGPL applies to Jan itself; we only send HTTP requests to it. |
| **GPT4All** ★ | `nomic-ai/gpt4all` | MIT | Local chat app with built-in document search, server on :4891. Simplest way to chat with your own files offline. |
| **KoboldCpp** ★ | `LostRuins/koboldcpp` | AGPL-3.0 | Single-file GGUF runner, server on :5001. Very forgiving on old GPUs and low-RAM laptops. |
| **text-generation-webui** ★ | `oobabooga/text-generation-webui` | AGPL-3.0 | Swiss-army UI over many loaders, API on :5000. Huge option surface; heavier than Ollama for the same result. |
| **Aphrodite Engine** ★ | `aphrodite-engine/aphrodite-engine` | AGPL-3.0 | vLLM fork tuned for single-GPU consumer cards, :2242. Better than vLLM on one gaming GPU. |
| **LM Studio** ★ | *(closed source)* | freeware (closed source) | Polished GUI with a local OpenAI server on :1234. NOT open source. Listed only so detection is honest: many people already run it. Free to use, no account needed for local mode. |
| **exo** | `exo-explore/exo` | Apache-2.0 | Runs one model across several machines on your desk, :52415. Two old laptops together beat one new one. Only worth it if you already own the hardware. |
| **llama-cpp-python server** | `abetlen/llama-cpp-python` | MIT | llama.cpp with Python bindings and a built-in OpenAI server, :8000. Use this when you want the engine inside your own Python script instead of a separate service. |
| **node-llama-cpp** | `withcatai/node-llama-cpp` | MIT | The same engine for JavaScript, with automatic GPU offload. Relevant only for the Electron-style side projects around JARVIS. |
| **TensorRT-LLM** | `NVIDIA/TensorRT-LLM` | Apache-2.0 | NVIDIA's fastest inference, compiled per GPU model. Highest speed on NVIDIA hardware, and the most setup pain. Needs a build step that is measured in hours, not minutes. |
| **LMDeploy** | `InternLM/lmdeploy` | Apache-2.0 | Efficient serving with strong quantisation support, :23333. Good middle ground: nearly vLLM speed with easier Windows install. |
| **Hugging Face Transformers** | `huggingface/transformers` | Apache-2.0 | Loads almost any open model into plain Python. The library every other project wraps. Slowest of the group because it is general, but the widest model coverage. |
| **Unsloth** | `unslothai/unsloth` | Apache-2.0 | Trains and fine-tunes small models on one consumer GPU. The free path to teaching a model your own writing style. Needs a GPU; nothing here is required for normal use. |
| **MiniCPM** | `OpenBMB/MiniCPM` | Apache-2.0 | Small strong models, some with vision, tuned for phones and laptops. Fits in 2-3 GB of RAM and still answers sensibly — the best fit for a low-spec laptop. |
| **Qwen** | `QwenLM/Qwen3` | Apache-2.0 | The strongest small open models for tool calling. Best free choice for reliable tool calls at 3-4B. Apache-2.0 weights, no usage policy attached. |


## Ears — 9 projects  
*Listen — turn speech into text*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **Vosk** ⭐ ★ | `alphacep/vosk-api` | Apache-2.0 | Streaming STT with partial results, 20+ languages, 50 MB models. What Arc Desk ships with: tiny, offline, no key, partial results for the wake word. |
| **sherpa-onnx** ⭐ | `k2-fsa/sherpa-onnx` | Apache-2.0 | STT + TTS + VAD + keyword spotting in one ONNX runtime, fully offline. The strongest single upgrade available: it can replace Vosk, the TTS and the wake word at once, with no PyTorch. |
| **whisper.cpp** | `ggml-org/whisper.cpp` | MIT | Whisper in C/C++, CPU or GPU, no Python needed. Much better accuracy than Vosk on accents and noise; needs a bigger model and more RAM. |
| **faster-whisper** | `SYSTRAN/faster-whisper` | MIT | Whisper re-implemented on CTranslate2, several times faster. Best accuracy-per-second on CPU if you can spare ~1 GB. |
| **OpenAI Whisper** | `openai/whisper` | MIT | The reference model and trainer (weights are MIT). The model is open. The *API* at openai.com is not — that stays blocked. |
| **Wyoming** | `rhasspy/wyoming` | Apache-2.0 | A tiny JSON protocol so STT, TTS and wake word become swappable services. Interesting if you ever want ears and mouth in separate processes; Arc Desk keeps them in-process today to save RAM. |
| **pyannote.audio** | `pyannote/pyannote-audio` | MIT | Speaker diarisation — who spoke when. Useful for meeting recordings, not for a single user talking to JARVIS. |
| **NVIDIA NeMo** | `NVIDIA/NeMo` | Apache-2.0 | Research-grade speech and language toolkit. Heavy (PyTorch first) but the accuracy ceiling is high. |
| **Mozilla DeepSpeech** | `mozilla/DeepSpeech` | MPL-2.0 | The project that proved offline STT was practical. Archived upstream since 2021. Listed because old tutorials still point at it — use Vosk or sherpa-onnx instead. |


## Mouth — 6 projects  
*Speak — turn text into voice*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **Piper** ⭐ | `rhasspy/piper` | MIT | Fast neural TTS, one ONNX voice per language, runs on a Pi. The natural next step after Windows SAPI: far more human, still offline. |
| **Kokoro** | `hexgrad/kokoro` | Apache-2.0 | 82M-parameter TTS that sounds close to paid cloud voices. Best free voice quality in 2026 for the size. ~350 MB of runtime. |
| **eSpeak NG** | `espeak-ng/espeak-ng` | GPL-3.0 | Robotic but indestructible formant synthesiser. Fallback of last resort: 2 MB, works on anything, sounds like 1985. |
| **Coqui TTS (XTTS)** | `coqui-ai/TTS` | MPL-2.0 | Voice cloning and many voices. Unmaintained upstream since 2024. Great results, abandoned project — use Kokoro unless you specifically need cloning. |
| **OpenVoice** | `myshell-ai/OpenVoice` | MIT | Clones a tone of voice from a few seconds of audio. Could give JARVIS a deeper, more 'manly' voice than a stock TTS. Clone only your own voice — not a stranger's. |
| **RVC voice conversion** | `RVC-Project/Retrieval-based-Voice-Conversion-WebUI` | MIT | Realtime voice-to-voice conversion on CPU or GPU. Post-processes any TTS into a chosen timbre. Same rule: your voice, your consent. |


## Wake — 3 projects  
*Always-on wake word, before anything else runs*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **openWakeWord** ⭐ | `dscripka/openWakeWord` | Apache-2.0 | Open wake-word models, 200 KB ONNX, runs on CPU in real time. You can train your own phrase instead of borrowing 'hey jarvis'. Ships a pre-trained hey_jarvis model. |
| **sherpa-onnx KWS** | `k2-fsa/sherpa-onnx` | Apache-2.0 | Streaming keyword spotting from the same sherpa-onnx runtime. One dependency for ears + wake word, instead of two. |
| **Picovoice Porcupine** | `picovoice/porcupine` | Apache-2.0 code, free tier needs an AccessKey | Very accurate wake word with a hosted console. Excluded as a default: the library is open but usage needs a Picovoice account and their free tier has terms. openWakeWord does the same job with no account, so that is what Arc Desk points at. |


## See — 9 projects  
*See — read screens, photos and documents*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **Tesseract OCR** ⭐ ★ | `tesseract-ocr/tesseract` | Apache-2.0 | Classic OCR engine; reads text out of any window or photo. Arc Desk already reads the screen with it. Small, offline, 100+ languages. |
| **PaddleOCR** | `PaddlePaddle/PaddleOCR` | Apache-2.0 | Much better accuracy than Tesseract on real-world photos. Handles rotated, blurry and mixed-language text far better. Heavier install (~500 MB with Paddle). |
| **EasyOCR** | `JaidedAI/EasyOCR` | Apache-2.0 | PyTorch OCR in 80+ languages with a two-line API. Easiest to start with; pulls PyTorch in. |
| **MarkItDown** ⭐ | `microsoft/markitdown` | MIT | Turns PDF, Word, Excel, PPT and images into clean Markdown. Would let JARVIS read any document with one function instead of the per-format readers it has now. Strong candidate. |
| **Docling** | `docling-project/docling` | MIT | Layout-aware document parsing: tables, columns, reading order. Best free extractor for messy PDFs with tables. Slower than a text reader, so only for files that need it. |
| **OmniParser** | `microsoft/OmniParser` | MIT | Turns a screenshot into a labelled list of clickable UI elements. This is how 'click the Save button' becomes reliable without a vision API. The most interesting row in this group. |
| **CLIP** | `openai/CLIP` | MIT | Matches images to text — search your photos by description. Enables 'find the photo with the red bike' over a local folder. Weights are MIT. |
| **Ultralytics YOLO** | `ultralytics/ultralytics` | AGPL-3.0 | Real-time object detection. AGPL: fine to run, awkward if you ever ship a modified version. Not needed for JARVIS's current jobs. |
| **Qwen2.5-VL** | `QwenLM/Qwen2.5-VL` | Apache-2.0 | An open vision model that can describe and reason about a screenshot. A real 'look at my screen and explain it' brain, fully offline, if you have ~4 GB spare. |


## Recall — 6 projects  
*Recall — remember your files. Retrieval and search*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **Chroma** ⭐ | `chroma-core/chroma` | Apache-2.0 | Embedded vector database — the easy default for local RAG. One folder, no server, no account. What JARVIS would use first for 'ask my documents'. |
| **Qdrant** | `qdrant/qdrant` | Apache-2.0 | Fast vector search server in Rust, :6333. Better than Chroma past roughly a million chunks; overkill below it. |
| **FAISS** | `facebookresearch/faiss` | MIT | The original similarity-search library. Fastest raw index, no frills: you store the text yourself. |
| **LanceDB** | `lancedb/lancedb` | Apache-2.0 | Columnar vector store that also keeps your metadata. Good when search results need filters like date or file type. |
| **txtai** | `neuml/txtai` | Apache-2.0 | All-in-one embeddings database with keyword + vector hybrid search. Hybrid search in one dependency — closest match to what Arc Desk's own file index does, but semantic. |
| **Unstructured** | `Unstructured-IO/unstructured` | Apache-2.0 | Chops PDFs, emails and HTML into clean chunks for indexing. The boring half of RAG that decides whether the answers are any good. |


## Flow — 5 projects  
*Flow — repeatable automation, not one-off commands*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **AutoHotkey** | `AutoHotkey/AutoHotkey` | GPL-2.0 | Windows hotkeys and macros in a scripting language. JARVIS already sends keystrokes itself; AHK is for macros you want to run with JARVIS closed. |
| **AutoKey** | `autokey/autokey` | GPL-3.0 | The same idea on Linux and X11 desktops. Kept for the small number of users running Arc Desk on Linux. |
| **Prefect** | `PrefectHQ/prefect` | Apache-2.0 | Schedules and retries multi-step jobs. If a nightly 'clean my downloads, back up notes' job grows past a few steps, this is the free scheduler for it. |
| **Browser Use** | `browser-use/browser-use` | MIT | Lets a model drive a real browser step by step. Similar ground to Playwright MCP, but in-process. Needs a capable local model to be useful. |
| **Skyvern** | `Skyvern-AI/skyvern` | AGPL-3.0 | Browser workflows that survive layout changes. Aimed at form-filling at scale; heavy for one desktop. |


## Tools — 9 projects  
*Act — extra tools, usually over MCP*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **MCP reference servers** ★ | `modelcontextprotocol/servers` | MIT | Filesystem, Fetch, Time, Memory, Git, Sequential Thinking. Arc Desk already speaks MCP: paste any command in Settings and its tools appear as mcp__<server>__<tool>. |
| **MCP Python SDK** | `modelcontextprotocol/python-sdk` | MIT | The protocol implementation Arc Desk's own MCP client follows. Our client is ~300 lines of stdlib JSON-RPC, written from the spec, so the app has no runtime dependency on this. Listed for reference. |
| **Playwright MCP** | `microsoft/playwright-mcp` | Apache-2.0 | Drives a real browser: click, type, screenshot, read the DOM. Gives JARVIS hands on the web without any paid API. |
| **GitHub MCP Server** | `github/github-mcp-server` | MIT | Issues, pull requests, code search, Actions. Needs a GitHub token — free, but an account. Off by default. |
| **Serena** | `oraios/serena` | MIT | MCP server that gives a model real code intelligence: symbols, refs. The best free way to make a small model useful on a real codebase. |
| **Playwright for Python** | `microsoft/playwright-python` | Apache-2.0 | Scripted browser control with no model needed. Deterministic: JARVIS records the steps once, replays them forever. |
| **Puppeteer** | `puppeteer/puppeteer` | Apache-2.0 | The JavaScript equivalent, driving headless Chrome. Only if the browser automation lives on the JS side. |
| **llm** | `simonw/llm` | Apache-2.0 | A command line for models, with plugins for local servers. Handy for testing what a local model can actually do before wiring it into JARVIS. |
| **awesome-mcp-servers** | `punkpeye/awesome-mcp-servers` | MIT | A hand-maintained index of MCP servers you can paste into Settings. Read it before writing a new integration — someone usually has one. |


## Glue — 15 projects  
*Support — runtime libraries the rest stand on*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **ONNX Runtime** | `microsoft/onnxruntime` | MIT | Runs the small speech models without PyTorch. The reason sherpa / openWakeWord start in milliseconds. |
| **python-sounddevice** ★ | `spatialaudio/python-sounddevice` | MIT | Microphone capture through PortAudio. What the wake daemon records with. One import, no visible window. |
| **Silero VAD** | `snakers4/silero-vad` | MIT | Voice activity detection, 1 MB ONNX. Stops the app listening to silence, so the CPU idles instead of working. |
| **pywinauto** | `pywinauto/pywinauto` | BSD-3-Clause | Windows UI automation for apps with no CLI. Optional reach: lets JARVIS press buttons in old Windows programs. Not bundled — it touches the desktop, and the guard treats that carefully. |
| **PyInstaller** ★ | `pyinstaller/pyinstaller` | GPL-2.0 with bootloader exception | Turns run.py into ArcDesk.exe. The exception is what makes shipping a closed or open app from GPL build tooling legal. |
| **psutil** ★ | `giampaolo/psutil` | BSD-3-Clause | CPU, memory, disk, battery and process stats on every OS. Every real number on the hologram comes from here. If it is missing, Arc Desk says so instead of inventing figures. |
| **pywin32** ★ | `mhammond/pywin32` | PSF-2.0 | Windows APIs: volume, brightness, clipboard, window handles. How JARVIS mutes, dims and locks without any external tool. |
| **mss** | `BoboTiG/python-mss` | MIT | Very fast cross-platform screenshots. About 10x faster than a naive grab — relevant if screen reading ever needs to run per frame. |
| **OpenCV (Python)** | `opencv/opencv-python` | Apache-2.0 | Image resizing, template matching, thresholding. Would replace the hand-written numpy work in the vision module with tested code. |
| **Pillow** ★ | `python-pillow/Pillow` | MIT-CMU | Image load, save and convert for every format. Behind every screenshot resize and OCR pre-process Arc Desk does. |
| **FFmpeg** ⭐ ★ | `FFmpeg/FFmpeg` | LGPL-2.1-or-later | The video and audio converter everything else calls. All video and audio work is handed to ffmpeg as a separate process, so none of it loads inside the Qt app. That is why RAM stays flat. |
| **watchdog** | `gorakhargosh/watchdog` | Apache-2.0 | Notifies you when files change, instead of polling. Would let the file index stay warm for free — currently it rescans on a timer. |
| **RapidFuzz** | `rapidfuzz/RapidFuzz` | MIT | C++ fuzzy string matching with honest scores. The command palette and file search both do fuzzy matching by hand; this would be faster and better at typos. |
| **websockets** | `python-websockets/websockets` | BSD-3-Clause | Clean async WebSocket client for streaming model output. Arc Desk streams with raw sockets today to stay dependency-free; this is the alternative. |
| **HTTPX** | `encode/httpx` | BSD-3-Clause | Modern HTTP client with timeouts done right. Same story: urllib is enough for local ports, httpx is nicer if that ever changes. |


## Ship — 3 projects  
*Ship — build, install and update the app itself*

| Project | GitHub | Licence | What it does for ARC |
|---|---|---|---|
| **Nuitka** | `Nuitka/Nuitka` | Apache-2.0 | Compiles Python to C — smaller, faster start than freezing. Alternative to PyInstaller if antivirus keeps flagging the PyInstaller bundle. Both are free. |
| **Inno Setup** | `jrsoftware/issrc` | Inno Setup licence (free, source available) | Makes a normal Windows installer and uninstaller. The polite way to ship Arc Desk: a real uninstaller in Add/Remove Programs, which is what uninstall.bat apologises for not having. |
| **uv** | `astral-sh/uv` | MIT / Apache-2.0 | Installs Python and dependencies in seconds. Makes the 'install JARVIS from source' path one command instead of five. |


---

## What is *not* in the list, and why

Refusing is a feature, and the reasons are written down instead of quietly omitted:

* **xtekky/gpt4free** — Routes your prompts through reverse-engineered endpoints to get paid models for free. That is evading someone's billing, not open source, and it breaks their terms. Arc Desk's whole point is that nothing is ever charged — not that someone else is charged instead.
* **Any 'unlimited API key' / cracked-key repo** — Same failure: stolen credentials. Also a security hole, since the traffic goes through whoever shipped it.
* **Anthropic/OpenAI/Gemini SDKs as the default brain** — Not refused as software — refused as a default. They are free to install and cost money the moment they answer, so the cost guard blocks them until you explicitly raise the limit.

## The honest caveats

* **Open source ≠ free of obligations.** AGPL projects (Jan, KoboldCpp, Aphrodite,
  text-generation-webui, YOLO, Skyvern) are free to *use*, and Arc Desk only sends
  HTTP requests to them. If you modify one and publish the result, its licence
  follows your code.
* **Model weights are a separate licence from the code.** Qwen and Mistral weights
  (Apache-2.0) are genuinely unrestricted. Llama weights carry a usage policy. Gemma
  weights carry Google's terms. Arc Desk never bundles weights — you pull them.
* **A closed app can still be useful.** LM Studio is listed because honesty beats
  tidiness: it is free to use, it is not open source, and detection says so.
* **Nothing here is vendored.** No third-party source code is copied into Arc Desk;
  every project is reached over a port, a CLI, or a normal import (see `CREDITS.md`).

## How Arc Desk chooses

1. **Fewest moving parts that still work offline.** That is why Vosk + Windows SAPI
   ship by default: two small pieces, no PyTorch, no service to babysit.
2. **Biggest upgrade per megabyte of RAM.** sherpa-onnx replaces ears, mouth and wake
   word with one Apache-2.0 runtime — the single best upgrade available.
3. **Nothing that needs an account to start.** Porcupine's free tier needs a Picovoice
   AccessKey, so openWakeWord gets the job instead.
4. **Never a paid default.** The cost guard (`arcdesk/ai/cost.py`) classifies every
   brain LOCAL and blocks anything metered until you opt in twice.
