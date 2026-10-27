# Arc Desk — your desktop, your universe

> Your desktop. Your universe. — one lightweight control panel, four power modes, zero
> copied Marvel assets: every pixel is painted by our own code.

**Status:** Phase 4 — installable application. Python 3.10+ · Windows 10/11 (also runs on Linux/macOS for dev).

---

## Run it

```bat
:: Windows — first time
install.bat

:: every time after that — double-click, no console window behind the app
ArcDesk.pyw
:: or, for autostart (starts hidden, opens with Ctrl+Alt+J)
start_arcdesk.vbs
:: or, if you want the terminal output while developing
python run.py
```

**Nothing ARC starts gets its own command prompt.** Speaking, screen reading, ffmpeg,
OCR, the local model and the wake daemon are all spawned through `arcdesk/quiet.py`
(`CREATE_NO_WINDOW`), and `tests/test_quiet.py` fails the build if a new call site
forgets. A windowless run writes to `%APPDATA%\ArcDesk\logs\arcdesk.log`.

Dev / QA helpers:

```bat
python run.py --mode gaming          :: boot straight into a mode
python run.py --screenshot shot.png  :: render a still frame and exit
python tools\bench.py --seconds 20   :: measure this app's own CPU + RAM
```

---

## What works right now

| Feature | State | Notes |
|---|---|---|
| ARC Core reactor | ✅ | Hand-painted rings, coils, arcs, orbit dots. No image assets. |
| Click core → cycle mode | ✅ | Focus → Chill → Gaming → Night. Saved to disk. |
| Right-click → quick menu | ✅ | Mode, pause animations, weather on/off, autostart, reset position, quit |
| Clock + date | ✅ | Fully offline, 1 repaint/second |
| CPU / RAM gauges | ✅ | psutil, non-blocking sampling once a second |
| Own footprint readout | ✅ | Shows Arc Desk's own MB in the HUD (honesty built in) |
| FPS cap readout | ✅ | Shows the current animation budget live |
| Weather | ⏳ optional | Open-Meteo, no API key. **Off by default** so the app never opens a socket. Cached; degrades to "offline" |
| App shortcuts | ✅ | 4 tiles. Right-click a tile to bind any .exe/.lnk/.bat. Persisted. |
| Power modes | ✅ | Each mode has its own palette, glow scale and frame cap |
| Tray icon + hide/show | ✅ | Drawn at runtime, no .ico file |
| Start with Windows | ✅ | HKCU Run key, uses `pythonw.exe` so no console flash |
| Settings persistence | ✅ | Atomic JSON in `%APPDATA%\ArcDesk\settings.json` |
| Auto-throttle guards | ✅ | Fullscreen game detected → 10 fps. On battery → 20 fps. |
| **ARC assistant console** | ✅ | Chat + tool calls, Ctrl+J. Runs on a worker thread, never blocks the UI. |
| **Hologram deck** | ✅ | wireframe globe + reactor core + live CPU/RAM/network/disk/process panels (real `psutil` telemetry), 12.7 ms per frame at 720p, no GPU, skips itself in Gaming mode |
| **Reads any file** | ✅ | pdf, docx, xlsx, pptx, csv/json, images (OCR), audio, video — then summarises, reviews and outlines it |
| **Edits any of them** | ✅ | resize/crop/trim/convert/gif/subtitles, docx find-replace, xlsx cells, pdf rotate/split/merge — always a **new** file |
| **Makes images and clips** | ✅ | free: local A1111/ComfyUI if running, otherwise a generated poster or a ken-burns clip that says what it is |
| **Video studio** | ✅ | 10 templates, 26 transitions, 17 looks, any aspect, burned titles, music with automatic ducking — local ffmpeg, originals untouched |
| **Audio studio** | ✅ | denoise, de-ess, gate, compressor, 3-band EQ, reverb, -14/-16 LUFS loudness, tempo without pitch shift, chapters, waveform, multi-track mix |
| **Backs up, and proves it** | ✅ | "back up my documents" — copies to another disk and SHA-256-verifies every file, with a manifest per run. A new folder every time, originals opened read-only, refusals for into-itself and for a disk that is nearly full |
| **Starts with you, if you say so** | ✅ | one per-user startup entry, no admin, read back to prove it, removable from the tray or Task Manager. Off unless ticked in the first-run wizard |
| **First run explains itself** | ✅ | five decisions with their real cost on each: voice, wake word (mic + daemon), autostart, document reading. Esc means "the cautious defaults" |
| **Explains why it is slow** | ✅ | "why is my laptop slow" — two measured samples a second apart, then the actual cause (RAM pressure, paging, a named CPU hog, a full drive, heat) with the number that proves it and ordered fixes. Never kills anything |
| **Searches inside your files** | ✅ | "which file mentions the Hampi advance" — reads the words inside Word, Excel, PowerPoint, PDF, CSV and text, and quotes the matching line with its number. Incremental, read-only, offline |
| **Reads your errors** | ✅ | "idhu enna error da" — typed, pasted, or OCR'd off the screen: 24 error families named with ordered fixes, and an honest "I do not recognise this one" for the rest |
| **Plays your media** | ✅ | "play ilaya nila" starts a real player (mpv/vlc/ffplay/mplayer/OS), prints the measured start time, and stops on command — no model, no network, one file at a time |
| **Scans external disks** | ✅ | "scan my E drive" indexes songs and videos read-only across every drive you own; an unplugged disk is reported, never silently swapped for the default folders |
| **Thinks before acting** | ✅ | "scan my external disk and play kabira" becomes two shown steps that really run, stopping at the first error |
| **Mentor · analyst · wellwisher** | ✅ | listens before it advises, gives options with trade-offs and a confidence line, journalling stays on your machine, and a crisis gets real helpline numbers |
| **Image studio** | ✅ | 16 looks, finished cards at exact platform sizes (post, story, thumbnail, passport), collages, whole-folder batch grading |
| **Medicine, with rails** | ✅ | urgency triage, 10 medicines with published label ranges, 8 body systems, first aid — never a personal dose |
| **Market, with arithmetic** | ✅ | quote, momentum, RSI, volatility, screener, **position sizing** — never a prediction sold as fact |
| **ARC Lite brain (offline)** | ✅ | 88 tools, rule-based intent matching. Works with zero setup, zero key, zero network. |
| **Reminders** | ✅ | "remind me in 20 minutes to stretch" — speaks once when the time comes, survives a restart, cancelled by number or by a word |
| **Focus blocks** | ✅ | real elapsed time, a local log, weekly totals; ARC stays quiet and says "take a break" at the end |
| **Morning briefing** | ✅ | one command: clock, calendar, reminders, focus minutes, CPU/RAM/disk — every line from a real source, and it says so when there is none |
| **File index** | ✅ | read-only search over your real folders by name, type, or words inside text files — never writes to your folders |
| **GitHub catalogue, in-app** | ✅ | 86 open-source packages: "which one can read a pdf?", "scan my stack", "what is missing in ears" |
| **Content studio** | ✅ | blog, reel, caption, email, ad, product, speech — outlines, drafts, 6 hook styles, hashtags, a posting calendar with real dates |
| **Marketing maths** | ✅ | funnel rates, CPC/CPL/CAC/ROAS, UTM links, SEO + Flesch readability of your own text, A/B sample size. No invented benchmarks |
| **Business strategy** | ✅ | SWOT, five forces, business model canvas, OKRs, break-even, LTV:CAC, weighted decision matrix — your facts, never invented ones |
| **Hotels and resorts** | ✅ | occupancy · ADR · RevPAR · TRevPAR · GOPPAR, menu costing to a food-cost target, housekeeping/front-desk SOPs, rate ladder |
| **Travel and maps** | ✅ | 92 places with real coordinates: "what is near Belagavi", distances by haversine, OpenStreetMap links with no key, itineraries, honest budget bands |
| **Design and craft** | ✅ | colour palettes with measured WCAG contrast, printable posters, kolam/rangoli patterns, borders, monograms — original SVG, offline |
| **Data mining** | ✅ | your own CSV/JSON: profile, Pearson r with n, IQR outliers, group-by, trend slope, one-command report |
| **Mentor mode** | ✅ | SCAMPER, six hats, inversion, five whys, pre-mortem, first principles, second-order thinking |
| **Honest foresight** | ✅ | least-squares extrapolation with an error band, three scenarios with stated assumptions, and a plain "I do not know" about live events |
| **Defensive security** | ✅ | your own password's entropy and crack time, phishing signals, this PC's posture, a recovery plan. **No cracking, no intrusion — refused in code** |
| **The library (88 tools)** | ✅ | 75 dated, sourced facts across 8 domains, your own indexed files quoted by name, and a live Wikipedia lookup that cites the date — or an honest "I do not know" with a search link |
| **Conversation mode** | ✅ | after a wake, six turns with no wake word; "thanks" ends it |
| **Streaming voice** | ✅ | speaks sentence 1 while sentence 2 is still generating (first word ~0.01 s in tests) |
| **Barge-in** | ✅ | talk over ARC and it stops mid-sentence |
| **Remembers you** | ✅ | `profile.json`: name, editor, city, reply language — learned from plain sentences |
| **Real LLM brain** | ✅ opt-in | Groq / Gemini / OpenAI + **9 local open-source backends auto-detected** (Ollama, llama.cpp, LocalAI, vLLM, Jan, GPT4All, KoboldCpp, text-gen-webui) |
| **MCP tool servers** | ✅ opt-in | plug any open-source MCP project from GitHub — files, git, sqlite, fetch, memory… as ARC's hands |
| **Automation tools** | ✅ | open apps, volume, media, brightness, screenshot, timer, notes, file search, clipboard, system report, lock, power (with confirmation) |
| **Voice output** | ✅ Windows | SAPI via PowerShell — no pip package, no extra RAM |
| **Voice input** | ✅ Windows | System.Speech dictation, offline |
| **Dangerous-action confirmation** | ✅ | shutdown / restart / kill app / sleep ask first, every time |
| Mini companion robot | ✅ painted | idle bob, blink, listening rings, thinking spin, speaking bars |
| **"Hey JARVIS" wake word** | ✅ opt-in | custom phrase, offline, runs in its own process (`arc_daemon.py`). Off until you arm it. |
| **Voice daemon** | ✅ | mic + Vosk in a separate PID; app-side is just one TCP socket |
| **Normal boot mode** | ✅ | Windows 11 stays 100 % untouched; Arc Desk waits hidden. `Ctrl+Alt+J` palette, `Ctrl+Alt+Q` quit |
| **Windows-untouched audit** | ✅ | `⋯ → Check: is my Windows untouched?` + `tools\desktop_check.py` scans our own source for desktop-altering APIs |
| **Command palette** | ✅ | type anywhere: `Ctrl+Alt+J` → one box → it runs |
| **Awakening sequence** | ✅ | full-screen cinematic when "Hey JARVIS" fires, then the app appears |
| **Website shortcuts** | ✅ | `open google`, `youtube`, `arena`, `github`… built into the offline brain |
| **Magic mode** | ✅ | "Hey JARVIS" → fullscreen ARC workspace + wallpaper swap. "BYE JARVIS" (or Esc) → everything back. Journaled, auto-restores after a crash |
| **Gravity Charms** | ✅ | floating robot / planet / car / butterfly / reactor on your desktop. Drag, wheel-resize, per-charm speed, positions saved. Click-through unless edit mode |
| **Installable .exe** | ✅ | `ArcDesk.exe` + `ArcDeskVoice.exe`, Inno Setup installer, Start Menu/desktop shortcuts, working uninstaller |
| **Settings window** | ✅ | voice, wake phrase, boot behaviour, hotkeys, charms, weather — no JSON needed |
| Gravity Charms / 3D objects | ✅ | |
| Transparent desktop overlay | ✅ | |

---

## Controls

| Input | Action |
|---|---|
| Drag header area | Move window |
| Left-click the core | Cycle power mode |
| Right-click window / core | Quick menu |
| `M` | Cycle power mode |
| `Esc` | Hide to tray |
| `Ctrl+J` | Open / close the ARC console |
| `Ctrl+Space` | Jump straight to the ask box |
| `Ctrl+Alt+J` | Command palette, works globally |
| `⋯ → Move / resize charms` | Charm edit mode (drag, wheel = size, right-click = menu) |
| `Ctrl+Alt+Q` | Quit everything, including the voice daemon |
| Say "Hey JARVIS" | The app comes to the front and enters magic mode |
| Say "BYE JARVIS" | Leaves magic mode, wallpaper restored, **and closes the app** (see below) |
| Click `WAKE OFF` | Arm / disarm the wake word |
| `⋯ → Test wake word` | Prove the voice path with no microphone |
| `Ctrl+Q` | Quit |

---

### Your voice out, your voice in

`arcdesk/clone.py` speaks ARC's words in a voice you import from a 10-second clip;
`arcdesk/voiceid.py` makes **this** machine accept commands only from the voice
enrolled on it. Both are honest about their limits — Tamil cloning needs IndicF5, a
GPU-sized model, and a voice lock stops your television, not a recording of you.

Scope is **Tamil, Hindi, English** — those three are promised and tested; the other
languages usually work but are never claimed. A clip is graded before it is used
(`good` / `short` / `workable` / `poor`) with a measured SNR, and
`tools\clean_voice.py` cleans a noisy one and proves the improvement.

```bat
AUTO-START.bat                                     :: start hidden with Windows (on/off/repair)
```

```bat
install_clone.bat                                  :: free engines, sizes shown first
python tools\voice_setup.py import "clip.mp4"       :: the reference clip
python tools\voice_setup.py try "vanakkam macha"    :: hear it
python tools\voice_setup.py lock-enroll me r1.wav r2.wav r3.wav
python tools\voice_setup.py lock-on
```

Full detail: `VOICE.md`. Two laptops keep two separate voice profiles unless you copy
them on purpose.

---

### A photo, or a drawing? It says which.

"draw an elephant" gives you a clean vector sketch — shapes, not skin. "**real photo of an
elephant**" gives you an actual photograph: `arcdesk/photo.py` searches Wikimedia Commons
(no key, no account, no GPU, ~1 s) and always prints the photographer, the licence and the
source page. Nothing is ever presented as a photo that was drawn, or the other way round.

| Ask | Result | Cost |
|---|---|---|
| "real photo of an elephant" | a real, freely-licensed photograph | internet |
| "make an image of an elephant" | a generated image | local diffusion backend + 4–8 GB VRAM |
| "draw an elephant" | vector sketch | nothing — offline, instant |

---

### Always there, waiting — and where your work goes

The app starts **silently** with your session (one per-user registry value, no admin, no
window, no taskbar entry) and waits for "hey jarvis". That is *silent start*, not stealth:
it appears in Task Manager → Startup apps like any other program, `Ctrl+Alt+Q` always
quits it, and uninstalling removes the entry. A process that hides itself and cannot be
killed is malware, whatever it is called — this one is not that.

Everything you do lives in the **Vault** (`arcdesk/vault.py`):

```
%APPDATA%\ArcDesk\vault\projects\<your project>\   project.json · notes.md · progress.jsonl · files\
```

- every answer is appended to the open project as it happens (**0.45 ms** per save)
- "export this project to my desktop" writes a **new timestamped, size-verified copy**
  anywhere you like — Desktop, Documents, `D:\Work`, a pen drive
- adding a file **copies** it; your original is never moved, renamed or overwritten
- Settings → Vault moves the whole vault to another drive

Measured answer speed (`python tools\speedcheck.py`): Lite brain **0.28 ms** p50,
routing **1.01 ms**, a tool call 0.01 ms. A local LLM still takes seconds — that number
belongs to `tools/bench.py`, not to this table.

---

### "Hey JARVIS" opens it, "BYE JARVIS" closes it — exactly

That is the promise, so it is a setting with three honest answers, and the default is the
literal one: **the application closes**.

| Settings → `On "BYE JARVIS"` | What happens | Use it when |
|---|---|---|
| **Close the app — launcher keeps listening** (default) | Window ends, a small launcher stays armed; "hey jarvis" starts it again | You want the voice to work in both directions |
| Close the app — nothing stays behind | Window ends, nothing listens; reopen from the shortcut | You do not want a background process |
| Hide to background | Window hides, tray icon stays | You want the fastest reopen |

Two guarantees around it:

- **It never quits into silence.** Before closing, the app proves a launcher is actually
  alive; if it cannot stay (no `sounddevice`, no speech engine, model missing) the app
  *keeps itself open* and says why in plain words. Closing and leaving you with nothing to
  call back would be worse than staying.
- **The same thing happens whether or not magic mode was on.** Saying "bye jarvis" used to
  only work mid-magic; now it always means "close".

Prove it on your machine, with the real app and the real protocol (no microphone needed):

```bat
python tools\voice_roundtrip.py
```

---

## Free — and enforced

Nothing in Arc Desk costs money. ARC Lite and all 12 local engines are **₹0 forever**, with no
account and no licence key. Paid providers are **blocked by a guard in the code** (not just a
promise), and the agent falls back to Lite if one is ever configured by mistake.

```bat
setup_free_ai.bat                  :: install Ollama + a free model, one click
python tools\free_ai_check.py      :: prove this setup cannot charge you
```

Full reasoning, limits and the honest downsides of local models: **`FREE.md`**.

## The performance budget (your #1 requirement)

Measured on this build, headless (so it is a *floor*, not a best case):

| Metric | Number |
|---|---|
| RAM, steady state | ~82 MB incl. charms — and **flat**: same after 0.3 s and after minutes |
| RAM floor of the stack itself | ~44 MB (Qt + Python), so our own UI + assistant costs ~34 MB |
| CPU, Chill (30 fps) | ~5.5 % of one core (+1.5 % with charms on screen) |
| CPU, Focus (20 fps) | ~3.3 % of one core |
| CPU, Gaming (10 fps) | ~2.2 % of one core |
| CPU, animations paused | ~1.6 % of one core |
| Memory growth over time | none observed (no leak path, no per-frame allocation) |

Why it stays this cheap — the four rules the code follows:

1. **One timer for the whole app** (`ticker.py`). Not one `QTimer` per widget.
2. **Static things are painted once into a `QPixmap`** and blitted. The reactor's halo,
   tick ring, coils and glow never rebuild a gradient during animation.
3. **Nothing is imported that we do not draw.** No Qt Quick / QML engine, no WebEngine,
   no OpenGL scene graph. (QML alone would have added ~35–50 MB before drawing anything.)
4. **Every mode has a frame cap and an effect scale.** Gaming mode is 10 fps and 15 % glow,
   so it cannot compete with a game for the GPU.

On a real Windows desktop expect ~75–95 MB total; add the guards above and it stays out of
the way. Full details and how to verify on your own laptop: `PERFORMANCE.md`.

**The assistant does not change that number.** The model never runs inside Arc Desk:
- Groq / Gemini / OpenAI → a JSON request from a worker thread
- Ollama → a *separate* process you can kill; its ~2.5 GB never lands in our app
- ARC Lite → pure Python regex against the tool registry

Adding the assistant cost **+4 MB** and the wake-word listener **+2 MB** (78.5 MB total), measured.

---

## Project layout

```
arcdesk/
  run.py                  launcher + CLI flags
  arcdesk/
    config.py             atomic JSON settings in %APPDATA%
    theme.py              the four power modes (palette + fps + effect scale)
    ticker.py             the single animation clock
    stats.py              psutil sampling (non-blocking)
    weather.py            optional, off by default, cached
    guard.py              fullscreen / battery auto-throttle
    autostart.py          HKCU Run key
    ai/
      agent.py            think -> tool -> answer loop (worker thread, max 4 rounds)
      backends.py         detects 9 local open-source engines on localhost
      mcp.py              MCP client: any open-source tool server as ARC's hands
      llm.py              one OpenAI-compatible client for 5 providers + auto-detect
      tools.py            86 automation tools, every one returns a string
      lite.py             the offline rule-based brain
      voice.py            SAPI text-to-speech + Windows dictation
      persona.py          ARC's voice and its rules about your machine
    tray.py               tray icon, drawn at runtime
    widgets/
      window.py           the ARC Control Center
      reactor.py          the ARC Core (3 cached layers)
      gauge.py            CPU / RAM rings
      hud.py              clock card + mode pills
      shortcuts.py        app shortcut tiles
      assistant.py        the console (transcript, chips, mic)
      companion.py        the painted robot
      aisetup.py          brain picker dialog
      awakening.py        the full-screen "magic begin" sequence
      palette.py          global command box (Ctrl+Alt+J)
      settings.py         the one settings window
      magicscreen.py      the fullscreen ARC workspace
    paths.py              source vs frozen .exe path resolution
    hotkeys.py            global hotkeys via RegisterHotKey (Windows)
    charms.py             Gravity Charms: painted sprites + click-through overlay
    magic.py              magic mode: wallpaper swap + crash-safe journal
    wake/
      client.py           app-side loopback listener (QTcpServer)
      daemon_runner.py    spawns / kills the voice daemon
      protocol.py         newline-JSON wire format
  arc_daemon.py           voice daemon: mic -> wake -> command -> app (own process)
  tools/bench.py          CPU/RAM measurement
  tools/                  bench, capability probe, live-model run, doctor,
                          packaging check, tools-reference generator, first-run smoke,
                          icon generator
  tests/                  agent-loop, file-brain, market, health, backup, packaging and
                          first-run tests (no key, no mic, no display)
  uninstall.bat           clean removal: processes, autostart, settings
  build/                  arcdesk.spec (two exes) + build.bat + arcdesk.iss (Inno Setup)
  TOOLS.md                every tool, generated from the registry
  shots/                  screenshots of all four modes
```

---

## Giving ARC a brain (optional)

Out of the box ARC runs in **Lite mode**: offline, no key, no model, and it still opens apps,
reports CPU/RAM, sets timers, takes screenshots, writes notes and switches modes.

To get real conversation and multi-step reasoning, open `⋯ → Assistant setup` and pick one:

| Option | Cost | Setup | Notes |
|---|---|---|---|
| **Local open source** | ₹0, offline | install Ollama / llama.cpp / LocalAI / vLLM | auto-detected, model RAM stays in *their* process. See `OPEN_SOURCE.md` |
| **Groq** | free tier | paste a key from console.groq.com | fastest free option, good tool calling |
| **Gemini** | free tier | paste a key from aistudio.google.com | strong reasoning |
| **Ollama** | free, offline | install Ollama, `ollama pull llama3.2:3b` | runs on your machine, ~2.5 GB in *its* process |
| **OpenAI** | paid | paste a key | most reliable |
| **Custom** | varies | set base URL | LM Studio, OpenRouter, vLLM — anything `/v1` |

Prefer environment variables over storing a key in settings: `GROQ_API_KEY`,
`GEMINI_API_KEY`, `OPENAI_API_KEY`. Press **TEST CONNECTION** before saving.

Auto-detect order: your key → Groq → Gemini → OpenAI → local Ollama → Lite. Anything that
fails mid-conversation falls back with an honest message instead of going silent.

## What ARC can actually do

Ask in plain language; ARC picks the tool:

`open notepad` · `what's my cpu usage` · `set volume 30` · `pause the music` ·
`brightness 50` · `take a screenshot` · `timer 10 minutes` · `note buy coffee` ·
`read my notes` · `find file report pdf` · `what's on my clipboard` · `lock the screen` ·
`how much ram is left` · `switch to night mode` · `what's the weather` ·
`shutdown` (asks permission first)

Safety rules baked in: `shutdown`, `restart`, `sleep` and `close_app` require an explicit
confirmation dialog every single time. ARC cannot silently power off your PC.

Known limits, stated plainly: `web_search` opens a browser but **cannot read the results
back** — the model is told this, so it will not pretend it searched. Voice output is
Windows-only via SAPI; on Linux/macOS it falls back to `say`/`espeak` or stays quiet.

## Verify the assistant without spending anything

```bat
python tests\test_agent_loop.py
```

Spins up a fake OpenAI-compatible server locally, makes the agent request the `time` tool,
feeds the result back and checks the final answer. No key, no internet — this is the exact
path that breaks silently in most assistant apps.

```bat
python run.py --ask "system report"     :: one-shot answer, prints to stdout
python run.py --console --demo-chat     :: see the console populated
python tests\test_wake_pipeline.py      :: wake word end-to-end, no microphone needed
python tests\test_lang.py               :: answers in the language you spoke
python tests\test_knows.py              :: exact maths, units, honest market data
python tests\test_macros.py             :: teach it a command, and what it refuses to learn
python tests\test_talk.py               :: conversation mode, barge-in, memory
python tests\test_stream.py             :: streaming speech against a real SSE server
python tests\test_welcome.py            :: first-run card: mic stays off unless chosen
python tests\test_reading.py            :: builds a real pdf/docx/xlsx/pptx/png/wav/mp4 and reads them
python tests\test_market.py             :: market maths is exact, market words never become advice
python tests\test_health.py             :: emergencies escalate, dosages refuse, unknown drugs refuse
python tools\say.py --voices            :: what your machine's voices sound like
python tools\doctor.py --deep          :: the 14 desktop tools + mic + wake, PASS/FAIL
python tools\model_bench.py            :: which local model should be the default
```

## Talking to it

**`COMMANDS.md`** lists every phrase ARC understands — including **"draw an elephant"**, what
it really draws, and how to edit the result by talking to it. `MCP.md` covers the nine extra
tool servers that turn on with one button.

## What it can actually do — measured

**`CAPABILITIES.md`** is the honest inventory: 59 actions with the latency each one took,
every automatic reaction, the skills that complete end to end, the four numbers that matter
(memory, CPU, tool latency, intent accuracy), and the seven flaws this audit found and fixed.

```bat
python tools\capability.py --all
```

## Validate the whole thing

```bat
check.bat                 :: or: python tests\run_all.py
```

72 tests, ~88 seconds, no key, no model, no internet, no microphone and no display needed.
They cover the agent loop, the wake pipeline, magic mode, MCP, backend detection, the cost
guard, the app lifecycle (open/close), the package catalogue, doc-to-code consistency, and
the crash log / single instance / doctor plumbing.

## Something not working? Run the doctor

```bat
python run.py --doctor
```

Fifteen read-only checks: Python version, Qt toolkit, settings folder and file, cost guard,
local engines, microphone library, wake engine, single-instance lock, packaged-vs-source build,
"Windows untouched" scan, disk space, crash log. It prints `[ok] / [warn] / [FAIL]` and fixes
nothing. The same thing is a button: **Settings → System → Run doctor**.

Crashes and Qt warnings go to `%APPDATA%\ArcDesk\logs\arcdesk.log` (API keys are scrubbed
before they are written). A packaged `.exe` has no console, so without this file a failed boot
would be invisible — **Settings → System → Open log** shows it.

**Portable mode:** set `ARCDESK_HOME=D:\ArcDesk` and every setting, log and cache lives in
that folder instead of `%APPDATA%` — good for a USB stick, and it is what the tests use so they
can never touch your real settings.

## The GitHub stack — 86 packages, all free

Every brain, ears, mouth, wake-word and tool project ARC can drive, with licence and port:
**`GITHUB.md`**. Check what is actually on your machine:

```bat
python tools\github_scan.py --all --plan
```

Ten groups, 86 projects: **brain** 21 · **ears** 9 · **mouth** 6 · **wake** 3 · **see** 9 ·
**recall** 6 · **flow** 5 · **tools** 9 · **glue** 15 · **ship** 3. 85 are open source; the one
closed app (LM Studio) is labelled as such, because detection should be honest even when the
answer is "that one is not open source".

`GITHUB.md` is **generated** from the catalogue, so the docs cannot drift:
`python tools\github_scan.py --md GITHUB.md`, and `tests/test_catalog.py` fails if it is stale.

Ask ARC directly, no terminal needed:

| You say | You get |
|---|---|
| "which open source package can read a pdf" | MarkItDown, Docling — with licences and why |
| "scan my github stack" | which of the 86 are on this PC right now |
| "what is missing in ears" | the exact free install commands for the speech stack |
| "how many packages are catalogued" | the real count, straight from the data |

Catalogue data: `arcdesk/ai/catalog.py` · questions answered by `arcdesk/ai/packages.py` ·
integrity enforced by `tests/test_catalog.py` and `tests/test_packages.py`.

## Install it as an application

```bat
packaging\build.bat          :: builds ArcDesk.exe + ArcDeskVoice.exe
packaging\make_installer.bat :: optional, free Inno Setup -> ArcDeskSetup.exe
```

Result: **"HEY JARVIS"** opens the ARC world fullscreen, **"BYE JARVIS"** closes it and puts
Windows back exactly as it was. Both behaviours are settings; the default keeps the app in the
background so reopening is instant. Step-by-step, including the first-run wake-word setup and
uninstall: **`INSTALL.md`**.

## Magic mode — the "total change"

Say **"Hey JARVIS"** → 1.9 s cinematic → **fullscreen ARC workspace** with your wallpaper swapped.
Say **"BYE JARVIS"** (or Esc, or `Ctrl+Alt+Q`) → wallpaper restored, charm overlay back, Windows
normal again.

Every change is journaled **before** it happens, so even a hard kill cannot leave your wallpaper
changed — the next launch repairs it. What we deliberately never do: replace Explorer, kill
`explorer.exe`, hide icons, or touch the taskbar's own settings. Those are the things that
actually break a Windows install.

Full explanation, risk table and audit notes: **`MAGIC.md`**.

## Normal boot — Windows untouched

```bat
start_arcdesk.vbs        :: silent launch: no console, no window
```

Your PC boots into **normal Windows 11 Pro**: same wallpaper, same desktop icons, Recycle Bin,
taskbar, Start menu, Explorer — all exactly as they were. Arc Desk waits in the background with
one tray icon (or none, if you set `"tray": false`).

Say **"Hey JARVIS"** → the screen transforms for ~1.9 s → the app lands, console open, ready for
your command. Press **`Ctrl+Alt+J`** any time to type instead. **`Ctrl+Alt+Q`** always quits.

You can verify the "untouched" claim yourself:

```bat
python tools\desktop_check.py --save   :: baseline
python tools\desktop_check.py          :: compare later -> UNTOUCHED or a named diff
python tools\desktop_check.py --scan   :: greps our source for wallpaper/taskbar/icon APIs
```

Full contract, write-paths table and the reasoning behind "silent, not stealth":
**`BOOT.md`**. Clean removal: `uninstall.bat`.

## Wake word ("Hey JARVIS")

Off by default — nothing touches your microphone until you arm it.

```bat
install_voice.bat                        :: vosk + sounddevice + the 40 MB model
```

Then click the **WAKE OFF** pill in the header. Say "Hey Jarvis", wait a beat, say your
command. The phrase is a config value, so you can change it to anything without retraining.
Full guide, engine comparison and troubleshooting: **`WAKE.md`**.

The daemon is a separate process on purpose: continuous listening needs 60–150 MB and a mic
device, and none of that belongs in the window process. The HUD shows both numbers live —
`ARC CORE nn MB` and `VOICE nn MB`.

## Packaging into one double-clickable installer

```bat
packaging\build_all.bat        :: one command, on a Windows build machine
-> dist\ArcDeskSetup.exe       :: the only file you carry
```

Everything is inside that one file: the app, its own Python (frozen by PyInstaller),
ffmpeg + ffprobe, and optionally Node for MCP tool servers. The person installing
double-clicks, gets **no admin prompt**, no Python/ffmpeg installation, no PATH editing,
and a last screen that says *"Arc Desk is installed successfully."*

| Piece | Where it comes from | Size |
|---|---|---|
| app (`ArcDesk.exe` + `ArcDeskVoice.exe`) | PyInstaller, two `EXE` targets | ~45–60 MB folder |
| ffmpeg + ffprobe | `packaging\fetch_runtime.py`, once, on the **build** machine | 195 MB → **58 MB** after lzma2 (measured) |
| Node (optional, `Components`) | same, only if you tick "MCP" | ~85 MB → ~30 MB |

Honest limits, unchanged:

- **PyInstaller cannot cross-compile.** This repo is developed on Linux, so the `.exe` is
  built on your Windows machine. `tools/packaging.py` reports that step as `UNVERIFIED`
  rather than pretending.
- the final `Setup.exe` size is printed by `packaging\build_all.bat` after Inno Setup runs; the
  lzma2 ratio above is the measured input to it, not the number itself.
- three compressions are refused on purpose: one-file packing (unpacks to `%TEMP%` on
  every launch), UPX (antivirus false positives), and cutting Qt modules the app uses.

## Every tool, written down once and generated

`TOOLS.md` lists all **86** tools with their arguments, which ones ask before acting, and
which are read-only. It is generated from the registry by `tools/gen_tools_doc.py`, so it
cannot drift — `check.bat` fails if the file is stale:

```bat
python tools\gen_tools_doc.py           :: rebuild TOOLS.md + arcdesk/TOOLS_PAGE.html
python tools\gen_tools_doc.py --check   :: exit 1 if either is out of date
```

The same data ships inside the app as a searchable page (`arcdesk/TOOLS_PAGE.html`) —
right-click the reactor → **What can I ask? (all of it)**. It works offline: no CDN, no web
font, no image, one file.

## Read these two pages before you ask for something impossible

- **`KNOWS.md`** — what "knows everything" means here: a sourced, dated library, your own
  indexed files, a live lookup that cites its date, and an honest "I do not know" for the
  rest. In Tanglish, because that is how we argued about it.
- **`REFUSED.md`** — every refusal, the reason, and the lawful thing built instead
- **`MACHI.md`** — the same thing in Tanglish: how the mentor/analyst modes think, the
  four honesty rules, the crisis numbers, and verbatim sample answers
  (hacking, cracking, covert access, personal medical doses, invented facts).

## Open-source usage, stated plainly

Arc Desk's UI, agent loop, tools, companion and daemon are **original work**. We use
open-source *engines as backend libraries* (Vosk, openWakeWord, PySide6, psutil) — never a
copy of somebody else's app, UI, or assets. Attribution and licences: **`CREDITS.md`**.

## Roadmap

See `ROADMAP.md`. Next up: Phase 5 — packaging on a real Windows box, keeping the same
"one timer, cached painting" rules so the budget does not move.
