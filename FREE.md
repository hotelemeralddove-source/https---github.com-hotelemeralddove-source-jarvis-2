# Free forever — what that actually means here

Your requirement: **no payment, no pricing, no subscriptions.** Short answer: **possible, and
it is the default.** But "free" has three meanings and they are not equal, so here is the
honest table.

| Path | Money | Account | Limit | Who does the work |
|---|---|---|---|---|
| **ARC Lite** | ₹0 forever | none | direct commands only | your CPU, no model |
| **12 local engines** (Ollama, llama.cpp, LocalAI, vLLM, Jan, GPT4All, KoboldCpp, text-gen-webui) | **₹0 forever** | none | your laptop's RAM/CPU | your GPU/CPU |
| **Groq / Gemini free tier** | ₹0 but rate-limited | yes, a key | requests/minute | their servers |
| OpenAI / paid APIs | 💰 per token | yes | — | their servers |

**Everything in Arc Desk itself is ₹0 and always will be:** the reactor, HUD, charms, magic
mode, wake word, voice in/out, the 25 automation tools, MCP tool servers, the settings app.
None of it phones home, none of it needs a licence key.

## The guard that makes it real

A promise in a README is worthless, so the code enforces it. `arcdesk/ai/cost.py` classifies
every brain before a request:

```
local   -> 127.0.0.1 / ARC Lite        allowed by default
free    -> Groq, Gemini                allowed by default (₹0, rate limited)
paid    -> OpenAI, cloud custom URLs    REFUSED by default
```

Checked in `LLMClient.from_config()`, i.e. **before** any network call. If a paid brain is
configured — a stale `settings.json`, a copied config, an AI tool trying to be clever — the
request is refused with a plain explanation and the agent **falls back to ARC Lite and keeps
answering**. Verified:

```
1) classification
  ollama   http://127.0.0.1:11434/v1      local  ✓
  groq     https://api.groq.com/...       free   ✓
  openai   https://api.openai.com/v1      paid   ✓
2) client construction under max_class=free
  openai key        REFUSED ✓   (nothing sent, nothing charged)
  paid custom url   REFUSED ✓
3) agent falls back instead of dying
  brain now: lite    answered anyway: True
PASS
```

## One-click free local AI

```bat
setup_free_ai.bat
```

1. installs **Ollama** (open source, MIT) via winget — or tells you the manual download link
2. pulls `llama3.2:3b` (~2 GB, one time, free)
3. runs `tools/free_ai_check.py` to prove Arc Desk can see it

If winget is blocked, step 2 is: download from ollama.com, run the installer, rerun the script.
No account, no card, no email.

## Check any time

```bat
python tools\free_ai_check.py
```

It prints which engines are running, whether your configured brain could cost money, the
current limit, and the free/paid table. Exit code 0 means you cannot be charged.

## Set the limit to "local only"

`⋯ → Settings… → Local AI & tools → Allowed brain cost → Local only — ₹0 forever, offline`

Then the guard refuses Groq and Gemini too: nothing leaves the laptop, ever.

## The honest bit about running local

Local is free but **not free of resource cost**:

| Model size | RAM while running | Speed on a normal laptop | Good for |
|---|---|---|---|
| 3B (llama3.2:3b, qwen2.5:3b) | ~2–3 GB | usable | commands, short answers |
| 7–8B | ~5–6 GB | slower | better reasoning, needs 16 GB RAM |
| 13B+ | ~9 GB+ | needs a GPU really | not recommended on a laptop |

That RAM is in **Ollama's process**, never in Arc Desk (which stays ~82 MB). You can quit the
engine and the app keeps working in Lite mode. That separation is the whole reason this design
exists.

Also honest: a 3B local model is **not** as clever as a big cloud model. It is fine at
"open google", "what is using my RAM", "set a timer", "summarise this note". For long reasoning
you will feel the difference — and that is the price of ₹0 and full privacy.

## If you want zero installs at all

Use **ARC Lite**. Nothing to download, nothing to run, no model, no account. It handles:
open apps and websites, CPU/RAM/disk/battery report, volume/mute/media/brightness,
screenshots, lock screen, timers, notes, file search, clipboard, mode switching, magic mode,
charms, weather (if enabled). That covers the everyday automation you asked for, offline, free.


---

Nothing in the 86-package GitHub catalogue needs money. Full list with licences:
**`GITHUB.md`**. Check your PC: `python tools\github_scan.py --all --plan`.
