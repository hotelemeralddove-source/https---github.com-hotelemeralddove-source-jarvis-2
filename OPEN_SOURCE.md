# Open-source AI backends and tools (all from GitHub)

Arc Desk does not bundle a model and does not copy anybody's app. It speaks the
**OpenAI-compatible HTTP API** and the **MCP** protocol, so any open-source project that
implements either one plugs straight in — you choose it, you own it, you can remove it.

> **Cost:** every engine below is free and open source, and every one of them runs on your own
> machine with no account. See `FREE.md` for the full ₹0 guarantee and the guard that enforces it.

## 1. Local AI brains — pick one, or none

All of these are real GitHub projects. Arc Desk detects them on localhost automatically.

| Project | GitHub | Default port | Licence | Notes |
|---|---|---|---|---|
| **Ollama** | `ollama/ollama` | 11434 | MIT | easiest: `ollama pull llama3.2:3b` and done |
| **llama.cpp server** | `ggml-org/llama.cpp` | 8080 | MIT | fastest CPU inference, single .exe + .gguf |
| **LocalAI** | `mudler/LocalAI` | 8080 | MIT | also does whisper + image models, docker friendly |
| **vLLM** | `vllm-project/vllm` | 8000 | Apache-2.0 | best with a GPU, serves big models well |
| **Jan** | `janhq/jan` | 1337 | AGPL-3.0 | desktop app with a local API server |
| **GPT4All** | `nomic-ai/gpt4all` | 4891 | MIT | light, on-device, simple |
| **KoboldCpp** | `LostRuins/koboldcpp` | 5001 | AGPL-3.0 | single exe, very forgiving on old laptops |
| **text-generation-webui** | `oobabooga/text-generation-webui` | 5000 | AGPL-3.0 | power user, many loaders |
| LM Studio | (closed UI, local server free) | 1234 | freeware | listed for completeness, not open source |

**Where to look:** `⋯ → Settings… → Local AI & tools → Scan for local AI backends`.
It TCP-probes every default port (250 ms each), reads `/v1/models`, and names what it found.
Nothing is installed or started by Arc Desk.

**How to wire one up (Ollama, the shortest path):**

```bat
:: once
winget install Ollama.Ollama
ollama pull llama3.2:3b

:: then in Arc Desk: Settings → Local AI & tools → Scan → "Use this brain"
```

**The budget rule still holds:** the model's RAM is in *their* process. Arc Desk stays at
~82 MB, and you can kill the backend whenever you want without touching the app.

## 2. MCP tool servers — any open-source tool, as ARC's hands

[MCP](https://github.com/modelcontextprotocol) is the open JSON-RPC standard for tool servers.
Arc Desk spawns a server as a child process, lists its tools, and offers them to the model as
`mcp__<server>__<tool>`.

In `Settings → Local AI & tools`, one server per line:

```
name: command arg1 arg2
```

Real examples (all open source, all on GitHub):

```
files:  npx -y @modelcontextprotocol/server-filesystem C:/Users/you/Documents
github: npx -y @modelcontextprotocol/server-github
fetch:  uvx mcp-server-fetch
memory: npx -y @modelcontextprotocol/server-memory
sqlite: uvx mcp-server-sqlite --db-path C:/Users/you/data.db
git:    uvx mcp-server-git --repository C:/Users/you/project
```

Arc Desk itself ships **no** server. You decide what runs on your machine, and `Save & restart
MCP` applies it without restarting the app.

Requires Node (`npx`) and/or `uv` (`uvx`). The settings tab shows which is present.

### Safety rules for MCP

- a server only starts if **you** listed it
- it runs as a child process; it dies when Arc Desk quits
- every call has a 30 s timeout, so a broken server cannot hang the agent
- results are truncated to 1500 chars before reaching the model
- a missing/broken server returns `ERROR: …` to ARC instead of crashing the app

## 3. Other open-source pieces already in use

| Need | Project | Licence |
|---|---|---|
| Speech to text | **Vosk** (`alphacephei.com/vosk`, `vosk-api`) | Apache-2.0 |
| Wake word | **openWakeWord** (`dscripka/openWakeWord`) | Apache-2.0 |
| UI toolkit | **PySide6 / Qt** | LGPL-3.0 |
| System stats | **psutil** | BSD-3 |
| Microphone | **sounddevice** | MIT |

Optional upgrades, explicitly opt-in because they cost RAM:

| Upgrade | Project | Cost |
|---|---|---|
| Better dictation | `faster-whisper` (MIT) | 80–300 MB in the daemon process |
| Exact Windows volume | `pycaw` (MIT) | ~2 MB |
| Local OCR for screenshots | `tesseract` + `pytesseract` | ~30 MB |

## 4. What this deliberately is not

- **not a copy** of any of those apps — we call their API, we do not ship their UI
- **not a wrapper that hides the model** — you can see the process in Task Manager
- **not auto-installing** anything: no downloads, no `pip install` behind your back
- **not sending your data anywhere** unless you configured a cloud provider — local backends
  keep everything on your machine

## 4b. Sources behind the library — attribution, not aspiration

The facts ARC answers from are not scraped into the repo; each entry is a short
paraphrase with its source named and its year attached. The sources it cites are:

| Source | Used for | Licence / terms |
|---|---|---|
| **Wikipedia REST API** (`en.wikipedia.org/api/rest_v1`) | live `fetch` lookups, cached for a week | text under **CC BY-SA 4.0** — ARC always prints the article URL, so the attribution travels with the sentence |
| **UN World Population Prospects** | population figures, with the year | free to cite |
| **RBI, GST Council, Ministry of Finance** | repo rate, GST slabs — always with the year | public information |
| **NOAA, IEC 80000, IETF RFCs, WHO/AHA guidance** | science, units, first aid | public standards |
| **Survey of India / Census** | coastline, largest state | public information |

Two rules that matter more than the content: **a drifting number is never printed
without its year**, and **a claim with no source does not enter the shelf** —
`tests/test_world.py` fails the build if either slips.

## 5. Tests that prove it works without installing anything

```bat
python tests\test_backends.py    :: fake llama.cpp on :8080 -> detected, picked, described
python tests\test_mcp.py         :: real stdio MCP handshake -> tools routed to the agent
```

Both pass offline with no model, no API key and no internet.


## Full package catalogue

`GITHUB.md` lists all 86 catalogued projects across 10 roles —
brain (21), ears (9), mouth (6), wake (3), tools (9), glue (15), see (9), recall (6), flow (5), ship (3) — with licences, ports and honest notes, including the closed-source ones and the
projects deliberately refused. Machine-checkable copy: `arcdesk/ai/catalog.py`
(nothing is installed or copied: this is a catalogue ARC can search and detect).
Scan your PC: `python tools\github_scan.py --all --plan`.
