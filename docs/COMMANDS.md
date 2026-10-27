# What ARC does when you say it

Every phrase below was run against the real code. `Lite` = works with **no model, no key,
no internet** (ARC Lite's intent matcher, 32/32 on the test suite). `Brain` = needs a local
engine (Ollama / llama.cpp) or a free-tier key, because it has to reason, not pattern-match.

---

## 0. Real photographs — "no, I meant a REAL elephant"

A drawing is a drawing. If you want a photo, ARC finds a **real photograph somebody
actually took**, free-licensed, and always tells you who took it.

| You say | What happens | Needs |
|---|---|---|
| **"real photo of an elephant"** | searches Wikimedia Commons, downloads the best freely-licensed photo, shows it on the easel, saves it to `Pictures\ArcPhotos\` | internet, no key, no GPU |
| "show me a real elephant photo" | same | internet |
| "picture of a tiger" | same | internet |
| "aane photo" | the Tamil word is mapped to `elephant` before searching | internet |
| "real photo of a red car please" | same, the polite words are stripped | internet |
| "make me an image of a dog" | **not** this — that is a generation request, it goes to `make_media` | local diffusion |
| "draw an elephant" | **not** this — that is the vector sketch engine | nothing |

Every reply names the file, the photographer, the licence and the source page, e.g.:

```
real photograph of african elephant: C:\Users\you\Pictures\ArcPhotos\african_elephant_….jpg
(1600×1067, 1132 KB) — File:Desert elephant (Loxodonta africana) spraying sand.jpg
by Charles J. Sharp, CC BY-SA 4.0. Source: https://commons.wikimedia.org/wiki/File:…
```

Three honest tiers for a picture, in the order ARC tries them:

| Tier | What you get | Cost |
|---|---|---|
| **1. `photo`** | a real photograph, real photographer, free licence | free, ~1 s, needs internet |
| 2. `make_media` | a *generated* image (photoreal-ish) | free, but needs a local diffusion backend and 4–8 GB VRAM |
| 3. `draw` | a clean vector sketch | free, instant, offline, no GPU |

Nothing here pretends tier 3 is tier 1. If the network is down, `photo` says so in one
sentence and points at the other two.

---

## 0b. Your voice — clone it, and lock the machine to it

| Command (in the project folder) | What it does |
|---|---|
| `packaging\build_all.bat` | Windows: builds both exes **and** `dist\ArcDeskSetup.exe` |
| `bash packaging/build_all.sh` | Linux/macOS/CI: same spec, same bundle, `dist/ArcDesk-linux.tar.xz` (not the Windows installer) |
| **Settings → System → "Visual effects"** | follow the mode / full / reduced / off — the one control that changes how much work a frame is |
| **Settings → Voice → "Voices…"** | two lists: who may command ARC, and which voice it answers in (any clip — yours, or someone else's) |
| **Setup card → "Add a brain…"** / **Settings → Local AI → "Add a brain…"** | downloads and starts a local model (Qwen2.5 1.5B, 1066 MB, tool-capable) on 127.0.0.1 — no account, no Ollama homework |
| `python tools/parity.py` | regenerates **WHATS_INCLUDED.md** — what ships, what to download, what never ships (`--check` verifies it is current) |
| **Settings → Local AI → "It calls itself:"** | the name it answers to — **JARVIS** by default |
| **Settings → Voice → "Get the ears ready…"** | ticks or crosses the four things "hey jarvis" needs, and downloads the 70 MB that can be fetched in-app |
| **Setup card → "Get the ears ready (70 MB)…"** | the same fix, offered right where the card says the machine cannot listen |
| **Esc** | anywhere in the app (a dialog → speech → the running task → console → hide → quit): stop speech → stop the running task → close the palette → close the console → hide the window |
| **Ctrl+Alt+H** | hide the window without touching a running task |
| **Console → STOP** | stop the current request between steps (the same action as Esc while busy) |
| **Settings → Voice → "Get the reply-voice engine…"** | IndicF5 (Tamil/Hindi, 1.5 GB) and XTTS (English, 1.9 GB), installed **from the app**, with live output and a Stop button |
| `python tools\voice_setup.py import "myclip.mp3" --transcript "the words"` | same thing from the command line |
| **Settings → Voice → "How ARC opens"** | desktop icon or voice — the same question the setup card asks |
| **Settings → Voice → "Teach ARC my voice…"** | 3 takes of 4 s, in the app; then the "only my voice" switch |
| `python tools\voice_setup.py selftest --against other.wav` | prove the lock with real audio: your held-out take must pass, another voice must fail |
| `python tools\voice_setup.py status` | what is installed, what is missing, which engine each language gets |
| `python tools\voice_setup.py import "clip.mp4"` | make the reference clip: trim, stitch, normalise, 24 kHz mono |
| `python tools\voice_setup.py import clip.wav --transcript "the words"` | same, and store what it says (IndicF5 needs it) |
| `python tools\voice_setup.py try "vanakkam macha"` | speak it in the cloned voice, right now |
| `python tools\voice_setup.py lock-model` | download the 30 MB speaker-embedding model |
| `python tools\voice_setup.py lock-enroll me r1.wav r2.wav r3.wav` | enrol **your** voice on this machine |
| `python tools\voice_setup.py lock-test r4.wav` | would this recording be allowed? prints the score |
| `python tools\voice_setup.py lock-on` / `lock-off` | enable / disable in settings |
| `python tools\move.py check` | what travels to another laptop, what is left behind, and why |
| `python tools\move.py pack D:\carry.zip` | one file with settings, vault and the clone clip (keys stripped) |
| `python tools\move.py unpack D:\carry.zip` | restore on the other machine (`--merge` keeps both) |
| `python tools\clean_voice.py "clip.mp3"` | clean a clip (hum, fan, hiss), tells you the grade before and after |
| `python tools\clean_voice.py clip.mp3 --import --transcript "…"` | clean **and** make it the clone reference in one step |
| `install_clone.bat` | install the free engines (piper, IndicF5, XTTS) with sizes shown |

The promise is **three languages**: Tamil and Hindi through IndicF5, English through
XTTS. Anything else is a bonus, never a claim.

Voice commands, once a clone engine is installed:

| You say | ARC answers in | Voice |
|---|---|---|
| "enne open pannu" (Tamil) | Tamil | your clone, via IndicF5 |
| "notepad kholo" (Hindi) | Hindi | your clone, via IndicF5 |
| "open notepad" (English) | English | your clone, via XTTS |
| any language, no engine installed | that language | Piper — real language, different voice, and it says so |

The wake word is checked the same way it always was; with **voice lock** on, the
*command* audio must also match the fingerprint enrolled on this machine.

---

## 0c. The cinematic cues, and the companion voice

Seven short cues, **generated inside the app on first launch** (0.15 s, ~90 KB total,
no download, no licence, no audio library — stdlib `wave` + maths only). They live in
`%APPDATA%\ArcDesk\sfx\`.

| When | Cue | Length |
|---|---|---|
| "hey jarvis" is heard | `wake` | 1.45 s |
| the window opens / magic mode begins | `magic_begin` | 1.50 s |
| magic mode closes, the app hides or quits | `magic_end` | 1.20 s |
| a task starts being processed | `task_start` | 0.28 s |
| the task finishes | `task_done` | 0.90 s |
| the task fails | `task_failed` | 0.55 s |
| a button is pressed (charms) | `click` | 0.12 s |

The phrases that make it a companion rather than a beep — all spoken **in your cloned
voice**, because they go through the same reply engine as everything else:

| Moment | It says |
|---|---|
| "hey jarvis" | **"Hi commander."** |
| you say bye / it is closing | **"Thank you, commander."** |
| "open notepad" | "Opening Notepad, commander." |
| "close chrome" | "Closing Chrome, commander." |
| "what is my cpu usage" | "Checking the machine, commander." |
| "set a timer for 10 minutes" | "Setting that up, commander." |
| "take a screenshot" | "Capturing the screen, commander." |
| "search for cheap flights" | "Searching, commander." |
| anything else it recognises as work | "On it, commander." |
| a question it has to think about | "Let me think about that, commander." |
| a job still running after 1.2 s | "Still on it, commander." (then rotates) |
| the job finishes / fails | a chime — it does **not** narrate (off by choice) |

| Command | What it does |
|---|---|
| **Settings → Sound → "Cinematic sound"** | on/off for all seven cues |
| **Settings → Sound → volume slider + "Hear one"** | set the level, then actually hear it |
| **Settings → Sound → "Companion voice"** | on/off for the spoken lines above |
| **Settings → Sound → "It calls you:"** | the honourific — `commander`, `sir`, your name, or blank to drop it |
| **Settings → Sound → "Preview the lines"** | every line, in order, before you commit |

Nothing here blocks the app: a cue is played on a daemon thread, a missing audio
device is swallowed silently, and a slow speech engine cannot delay the close.

---

## 0d. No command prompt behind the app — ever

ArcDesk is windowless by design (no black box, no `console` in the exe). The side effect
used to be that **every** console program it started got its own brand-new black window:
speak a sentence (PowerShell SAPI) — one window; read the screen — another; ffmpeg,
tesseract, a wake-daemon restart — another each. That is the "neraya command prompt open
aaitae iruku" problem.

`-WindowStyle Hidden` never fixed it, because PowerShell creates and shows the console
*before* applying the style. The fix is `CREATE_NO_WINDOW` on the spawn itself, in one
place (`arcdesk/quiet.py`), used by **95 spawn sites across 24 modules**.

| How you start it | What you see |
|---|---|
| double-click **`ArcDesk.pyw`** | the app, and nothing else (`pythonw.exe` runs `.pyw`) |
| double-click `ArcDesk.exe` (installed) | the app, and nothing else (`console=False`) |
| `python run.py` in a terminal | that terminal (yours), and **no extra windows** |
| anything ARC does afterwards — speaking, screenshots, ffmpeg, OCR, model server, wake daemon | **nothing** — every child is spawned silent |

| Where it lands | Why |
|---|---|
| `%APPDATA%\ArcDesk\logs\arcdesk.log` | `pythonw.exe` has no console: anything the app prints, plus a traceback if it ever dies, goes here |

| Command | What it does |
|---|---|
| `python tests\test_quiet.py` | proves it: the flag translation, a real child still answering, and a source scan that fails if any module starts a console child behind the app |
| `python -c "from arcdesk import quiet; print(quiet.describe())"` | one line: how many spawn sites are routed through the silent layer |

---

## 0e. When the installer itself will not start

`AppInstallerPythonRedirector.exe — 0xc0000142` is a **build-machine** fault: the exe was
made with the Microsoft Store's Python alias, or the PC has no MSVC runtime. Neither is
something the app can fix from inside a window that never opened.

| Double-click this | What happens |
|---|---|
| **`ArcDeskDiag.bat`** | no Python, no install: writes ArcDeskDiag.txt — blocked download? Store alias? runtime missing? already installed? — and offers to unblock the files |
| **`ArcDesk-portable.zip`** → Extract All → **`ArcDesk.exe`** | use it today, nothing installed, no Python needed |

If you are the one building it:

| Command | What it does |
|---|---|
| `python tools\preflight_win.py` | judges the machine **before** PyInstaller: Store alias, 32-bit, old Python, MSVC runtime, PySide6, PyInstaller, Inno Setup, disk, OneDrive/long paths. Exit 1 with the fix printed |
| `packaging\build_all.bat` | runs that same check as step 0, then builds; it cannot be skipped |
| `python -m pip install -r requirements-build.txt` | the build-only dependency (PyInstaller) |

The full dialog-by-dialog table is in **TROUBLESHOOT.md**.

---

## 1. Drawing — the thing you asked about

| You say | What happens | Needs |
|---|---|---|
| **"draw an elephant"** | ARC builds a vector sketch, puts it on the easel window and saves a PNG to `Pictures\ArcArt\` | **Lite** |
| "draw a cat in orange" | same, in orange | Lite |
| "sketch a house" / "paint me a tree" | same | Lite |
| **"make it purple"** | recolours the same drawing, saves a new version | Lite |
| **"make it bigger"** / "smaller" | scales 1.22× per step, clamped 0.42–1.9 | Lite |
| **"add a sun"** / "add a cloud" / "add a tree" / "add a star" | adds scenery beside it | Lite |
| "move it left" / "right" / "up" / "down" | repositions | Lite |
| "rotate it" | −12° each time | Lite |
| "undo" | reverts the last change | Lite |
| **"turn it into a house"** | changes the subject, keeps the palette | Lite |
| "draw a dragon" | says exactly which 10 things it can draw, and offers the upgrade path | Lite |

**How it draws:** not a diffusion model. `arcdesk/art.py` is a tiny drawing language — each
subject is a list of primitives (ellipse, rounded rect, polygon, bezier) in 0..1 space, painted
with QPainter at any resolution, in about 3 ms, with zero downloads and zero VRAM.

**How it edits:** the document is the state: `{subject, accent, scale, dx, dy, rotate, extras,
history}`. "Make it purple and bigger" changes three fields and re-renders. That is why undo is
free and why editing does not drift or hallucinate. The easel window (`widgets/artview.py`) has
a text line for the same edits by typing.

**If you want photorealistic images:** run ComfyUI (`:8188`), Automatic1111 (`:7860`),
Fooocus (`:7865`) or InvokeAI (`:9090`) — all free — and ARC detects the port and says so when
it draws. Without one, it draws a clean vector sketch instead of pretending.

---

## 2. Songs, videos, disks — and asking ARC to think

| You say | What happens | Needs |
|---|---|---|
| **"play ilaya nila"** | finds the file, starts mpv (or vlc, ffplay, mplayer, your OS player) and prints `started in N ms` | **Lite** |
| **"song podu"** / "paatu podu anirudh" | plays the most recently added track, or everything by that artist | Lite |
| **"play the video hampi trip"** | restricts the search to video files | Lite |
| **"stop the music"** | kills the process group and reports how long it played | Lite |
| "next song" / "previous" / "pause" | the OS media keys, for players ARC did not start | Lite |
| **"what is playing now"** | the file name, the player, and the elapsed seconds | Lite |
| **"scan my external disk"** | read-only index of every removable drive — or a plain "no external disk is attached" | Lite |
| "scan d drive" / "scan e disk" | just that drive | Lite |
| **"what songs do i have"** | the index, by count and kind | Lite |
| "do i have a song called nee" | phrase → token → fuzzy search, with the real path | Lite |
| **"scan my external disk and play kabira"** | the planner runs step 1, then step 2, and shows both | Lite |
| **"help me decide whether to raise prices"** | a decision frame: reversible? optimising what? cost of waiting? — plus a confidence line | Lite |
| **"mentor me on direct bookings"** | one frame, one action for today, and a request for the constraint it does not know | Lite |
| "i feel low today" / "romba stress da" | listens first, asks one question, answers in the language you used | Lite |
| "journal this: ..." / "check in with me" / "reflect on my week" | a local `journal.jsonl` and a count that only uses real entries | Lite |
| **"back up my documents"** | copies to the external disk, hashes every file on the destination, and says `verified: all N matched` — never overwrites, never touches the originals | Lite |
| "back up my pictures to D:\\Backups" / "back up from ~/Work" | same, with the source and target you named | Lite |
| **"verify the backup"** | re-hashes an old backup against its own manifest and names anything that changed | Lite |
| "which disks can i back up to" | the volumes it can see, with free space | Lite |
| **"start with windows"** / "stop starting with windows" | one per-user startup entry, no admin, removable in Task Manager | Lite |
| **"why is my laptop slow"** / "yen slow da" | two measured samples, then the real cause with the number that proves it, plus ordered fixes | Lite |
| **"my laptop is heating up"** / "the fan is loud" | thermal reading if the machine exposes one — and an honest "I cannot see it" if it does not | Lite |
| "what's slowing my pc" / "computer romba slow" | same, cause-first, severity-ranked | Lite |
| **"startup items"** / "what starts at login" | every Run-key entry, read-only, with the ones you should not disable | Lite |
| "pc health quick" | one line: `CPU 1% · RAM 45% · disk 80% free · fine` | Lite |
| **"index my documents"** | reads Word, Excel, PowerPoint, PDF, CSV and text from Documents/Desktop/Downloads — read-only, ~14 ms for a small folder | Lite |
| **"which file mentions the hampi advance"** | the file, the **line number**, and the sentence around it — quoted from your own document | Lite |
| "which documents talk about the invoice" / "where did i write about the rooftop cafe" | same, phrased the way people ask | Lite |
| "search inside my documents for discount" / "search my pdfs for gst" | content search, not filename search | Lite |
| "index my documents with ocr" | adds images and scanned pages — about a second each, said before it starts | Lite + Tesseract |
| "what is in my document index" | count, file types, when it last ran, what it skipped | Lite |
| "forget my document index" | deletes the index file only — never a document | Lite |
| **"idhu enna error da"** / "what is this error" | names the error, explains the cause, lists ordered steps — from the text you pasted, your clipboard, or an OCR of the screen | Lite |
| **"what is this error on my screen"** | screenshots, OCRs, and diagnoses what it reads | Lite + Tesseract |
| "explain this error, then paste the message" | 24 error families: Windows codes, Python, git, DNS/TLS/404, ffmpeg, locked files, USB disks | Lite |
| "why did it crash" / "why is this not working" | reads the message it can see — and says plainly when it cannot name it | Lite |

---

## 3. The rest of the commands

| You say | ARC does | Tool | Works in |
|---|---|---|---|
| "open notepad" / "launch chrome" | launches it | `open_app` | Lite |
| "open google" / "go to youtube" / "visit github" | opens the site | `open_url` | Lite |
| "search for best laptops" | opens a browser search (**cannot read results** — add the Fetch MCP server) | `web_search` | Lite |
| "how is my cpu doing" / "system report" | CPU, RAM, disk, battery, heaviest process | `system_report` | Lite |
| "what's using my ram" | top processes by memory | `running_apps` | Lite |
| "close spotify" / "kill chrome" | asks first, then terminates | `close_app` | Lite |
| "set volume to 40" · "mute" | audio | `set_volume`, `mute` | Lite |
| "play next song" / "pause" | media keys | `media` | Lite |
| "brightness 70" | display | `brightness` | Lite |
| "take a screenshot" | saves a timestamped PNG | `screenshot` | Lite |
| "lock my screen" | locks the session | `lock_screen` | Lite |
| "shut down the pc" / "restart" / "sleep" | asks first | `power` | Lite |
| "timer 10 minutes" | countdown + notification | `timer` | Lite (window open) |
| **"hey jarvis"** | cinematic → wallpaper → fullscreen ARC world | `magic` | Lite |
| **"bye jarvis"** | wallpaper restored → app hidden or exits | `magic` | Lite |
| "show charms" / "hide charms" | floating desktop objects | `charms` | Lite |
| "focus mode" / "night mode" | changes ARC's own appearance | `arc_mode` | Lite |
| "note that I need milk" / "read my notes" | one notes file | `note`, `read_notes` | Lite |
| "find report.docx" / "where is budget.xlsx" | read-only file index over your real folders, name and type aware, optional full-text | `find_file` | Lite |
| "copy this" / "what's on my clipboard" | clipboard | `clipboard` | Lite |
| "what's the weather" | needs internet + opt-in (off by default) | `weather` | Lite |
| "what time is it" | local clock | `time` | Lite |
| "which MCP servers are up" | lists them | `mcp_servers` | Lite |
| "remind me in 20 minutes to stretch" / "at 6:30 to call amma" | a reminder that speaks when the time comes, saved across restarts | `remind` | Lite |
| "show my reminders" / "cancel reminder stretch" | list or cancel by number, id or a word from the text | `remind` | Lite |
| "start a focus session for 25 minutes" / "focus on the invoice report for 50 minutes" | countdown, a local log, weekly totals | `focus` | Lite |
| "how long is left in focus" / "focus stats this week" | real remaining time and measured totals | `focus` | Lite |
| "good morning" / "brief me" | clock, calendar, reminders, focus, CPU/RAM/disk — every number real | `briefing` | Lite |
| "what is on today" | date, calendar and reminders only | `briefing` | Lite |
| "which open source package can read a pdf" | ranked answers from the 86-package GitHub catalogue, with licences | `packages` | Lite |
| "scan my github stack" / "what is missing in ears" | what is installed on this PC, and the exact free install commands | `packages` | Lite |
| "write a blog post about direct bookings" / "hashtags for hotel marketing" | outline + draft, word budget, 6 hook styles | `content` | Lite |
| "content calendar for 2 weeks" | real dates, weekends left for replies | `content` | Lite |
| "funnel 20000 impressions 400 clicks 60 leads 12 sales spend 5000 revenue 24000" | CTR, CPC, CPL, CAC, ROAS, each with its formula | `marketing` | Lite |
| "is this message phishing: …" | scored signals with reasons, never a verdict | `secure` | Lite |
| "how strong is my password …" | entropy + crack time at two attack rates; never stored | `secure` | Lite |
| "secure my pc" | Defender, firewall, encryption, last update — read-only | `secure` | Lite |
| "swot for my homestay" / "break even 90000 750 320" | canvas of real questions, or exact arithmetic | `strategy` | Lite |
| "occupancy 24 rooms 17 sold 42500 revenue" | ADR, RevPAR, TRevPAR, GOPPAR | `hotel` | Lite |
| "menu cost rice 2*60; dal 1*110" | ingredient total and the price the plate needs | `hotel` | Lite |
| "what is near Belagavi" / "map of Hampi" / "distance from Belagavi to Hampi" | haversine distances and real OSM links | `travel` | Lite |
| "plan a 3 day trip to Coorg" / "where should I go for a beach trip" | itinerary from real coordinates, or ideas by mood | `travel` | Lite |
| "make a kolam" / "design a poster for my cafe" / "colour palette" | original SVG in the craft folder | `craft` | Lite |
| "analyse sales.csv" / "correlate price units in sales.csv" | profile, r with n, outliers, trend | `mine` | Lite |
| "mentor me on pricing" / "pre-mortem: open a second property" | the frame, the questions, the next action | `mentor` | Lite |
| "forecast 120 140 155 171 190" | slope, r², error band — labelled arithmetic | `foresight` | Lite, Brain |
| "what happened in the market today" | an honest "I have no live feed", plus how to check | `foresight` | Lite |
| "hack my neighbour's wifi" | refused, with the legal reason and what to do instead | `secure` | Lite |
| "explain this error", "write a reply to this email", "plan my week" | real reasoning | *brain* | Brain |

---

## 2b. Doing work on the desktop (new)

| You say | What happens | Gate |
|---|---|---|
| "type good morning" | types into the focused window | — |
| "press ctrl s" | sends the chord | — |
| "open notepad and type hello" | two actions from one sentence, 1.5 s apart | — |
| "list windows" | titles of everything open | — |
| "switch to chrome" / "minimize everything" | focuses / minimizes | — |
| "create folder projects" | makes the folder in your home | — |
| "write hello to the file notes.txt" | writes it (old version kept as `.bak`) | — |
| "read the file notes.txt" | prints up to 200 lines | — |
| "delete the file notes.txt" | moves it to the trash | **asks first** |
| "run command echo hi" | runs it, output capped | **asks first** |
| "what did you do" | last 20 actions from the journal | — |

| "what's on my screen" / "what does the error say" | OCR of the screen | — |
| "click Save file" | finds the words on screen and clicks them | — |
| "email raj@x.com about the invoice" | sends through your SMTP account | **asks first** |
| "what's on my calendar" | next 7 days from your `.ics` files | — |
| "add a meeting at 4pm tomorrow" | writes a real `.ics` event | — |
| "whatsapp +91... saying I'm late" | opens the message, pre-filled | **asks first** |

Window, typing and key tools are Windows-first (PowerShell); on Linux they need
`xdotool` and say so. Full reasoning in `CAPABILITIES.md` §6.

---

## 2c. Numbers, markets and things it learns (new)

| You say | What happens | Needs |
|---|---|---|
| **"what is 18% of 4500"** | `calc` — exact, 810. Never a language model's guess | **Lite** |
| "convert 5 km to miles" | `convert`, with unit kinds checked (`kg`→`km` is refused) | **Lite** |
| "what is the dollar rate" | `rates`, live FX, shows the timestamp from the source | internet |
| **"nifty price"** / "sensex" / "bitcoin" / "reliance" | `stock` — last price, today, 30-day move, day range | internet |
| "predict reliance for 5 days" | `project` — a straight line through past prices with a ±2σ band, explicitly labelled a trend | internet |
| **"market eppadi"** | `market_summary` — NIFTY, SENSEX, gold, USD/INR, BTC in one screen | internet |
| **"when I say work mode, open code and set volume 40"** | `teach_macro` — learns it. Destructive steps are refused **at teach time** | **Lite** |
| "what have I taught you" / "forget work mode" | `macros` — list, run or forget | **Lite** |
| "which tools do you have" / "what can you do with files" | `list_tools` — the whole catalogue; the model only gets a shortlist per request | **Lite** |

Why the numbers are tools and not prose: a 0.5B model that was asked to add 18%
confidently answered a wrong number in testing. `knows.py` computes it, `stock()`
ends with *"information, not investment advice"*, and `project()` says out loud
that it is a line through the past, not a prediction.

---

## 2d. Talking to it like a person (new)

| You say | What happens |
|---|---|
| *(after any answer)* "and the sensex?" | **conversation mode** — no wake word needed, up to 6 turns |
| "thanks" / "seri podhum" / "theek hai" / "nothing else" | closes the conversation and returns to wake-word-only |
| *(talking while ARC speaks)* | **barge-in** — ARC stops instantly and listens to you instead |
| "my name is Arun" | remembered in `profile.json`, used in every later answer |
| "i use VS Code" / "I live in Belagavi" / "reply in tanglish" | same — durable preferences, not notes |
| "what do you remember about me" | `profile` tool prints every field |
| "forget my name" / "clear my profile" | removes it, immediately |
| **"what does this error say"** / "what is on my screen" | `look` — screenshot, OCR, then answer from the text it read |

A note on the last one: `look` reads *text*. It cannot describe a photo or a game
frame; it says so instead of inventing something.

---

---

## 2e. Files, media, medicine and markets (new)

Everything below works **typed or spoken**, in English or Tanglish, and every file
operation writes a **new** file — nothing you own is ever overwritten.

### Any file — read it, judge it, change it

| You say | What happens |
|---|---|
| **"summarise invoices/q3.pdf"** | `read_file` — per-page text, then an extractive summary that quotes the file |
| "what is missing in report.docx" / "review this deck" | `read_file mode=review` — *what is there / what is missing / what to improve / what to add*, each line citing a number from the document |
| "outline the contract" | `read_file mode=outline` — headings, or the first line of every block |
| "read shot.png" | OCR, with the image upscaled 2× first (`HELLO ARC DESK 2026`, not `DESK 2028`) |
| "summarise sales.xlsx" | column statistics: min → max, mean, total, blanks, distinct values, per sheet |
| "what is in clip.mp4" | container, codec, resolution, fps, duration — **and it says it cannot hear the words** |
| **"resize photo.png to 400x300"** | `edit_file` → `photo_resize_<timestamp>.png` |
| "trim clip.mp4 to the first 10 seconds" | `edit_file op=trim duration=10` → new mp4 |
| "make a gif from clip.mp4" | `edit_file op=gif` → new gif |
| "convert tone.wav to mp3" | `edit_file op=convert fmt=mp3` |
| "replace Revenue with Income in report.docx" | run-safe find & replace → `report_edited_<timestamp>.docx` |
| "set Sales!D1 to Margin" | `edit_file op=set_cell` → new workbook |
| "rotate doc.pdf 90 degrees" / "split pages 1-3" | pdf rotate / split / merge / extract |

### The hologram deck

| You say | What happens |
|---|---|
| **"show me the hologram"** / "holo deck" / "server view" | opens the fullscreen projection: globe, core, live telemetry, spectrum, event ticker |
| "close the projector" / Esc | dismisses it |
| Tray → "Hologram deck" | same thing without saying a word |
| *(magic mode)* | "hey jarvis" opens it as the surface of the magic screen, with the app buttons and input floating over it |

### Making pictures and clips — free, no key, no upload

| You say | What happens |
|---|---|
| **"make a video of an arc reactor glowing"** | ken-burns motion clip from generated stills → `arc_video_<timestamp>.mp4` |
| "generate an image of a golden arc reactor" | local diffusion if A1111/ComfyUI is running, otherwise a generated poster (`arc_poster_*.png`) that **says what it is** |
| "restyle shot.png like a blueprint" | image-to-image with a backend, tinted restyle without one |

To get real AI imagery, start Automatic1111 with `--api` (or ComfyUI) — ARC probes
`127.0.0.1:7860` / `:8188` before every request and reports which tier it used.

### Medicine — information, never a prescription

| You say | What ARC gives |
|---|---|
| **"i have chest pain and left arm pain"** | EMERGENCY · call 112 / 108 · why that pattern is treated as a heart attack until proven otherwise |
| "sore throat for two days" | urgency level + what to track + when to escalate |
| **"what medicine for fever"** / "paracetamol dosage" | the **published adult label range**, the warnings on the label, and a pharmacist — **never a dose computed for you** |
| "amoxicillin" | flagged PRESCRIPTION ONLY; the dose is a clinician's decision |
| any other drug | *"I do not have verified information for that, and I will not guess"* |
| "how does the kidney work" | anatomy: what it does, common problems, why, how it is investigated |
| "first aid for a burn" / "cpr" | step-by-step, with the emergency line first |

10 medicines with verified ranges, 6 emergency patterns, 8 body systems, 6 first-aid
guides. Every answer ends with *"not a diagnosis and not a prescription"*.

### Markets — measurement, arithmetic, and an honest "I don't know"

| You say | What ARC gives |
|---|---|
| "analyse reliance" | trend (20/50-day), 30-session move, position in the 60-session range, RSI(14), annualised volatility, worst drawdown |
| **"should i buy reliance"** | the measurements above + what a position would *risk* — never a recommendation |
| **"position size for 100000, 1% risk, 4% stop"** | exact unit count, exposure and exposure % — pure arithmetic |
| "watch tcs" / "watchlist" | saves / lists symbols with today's move |
| "screen reliance, tcs, infy for oversold" | filters by a measurable rule (`uptrend`, `oversold`, `near_high`, …) |
| "market eppadi" | brief: NIFTY, SENSEX, gold, USD/INR, BTC |

Why it is built this way: *"what should I buy"* is not answerable by software, and an
assistant that pretends otherwise is dangerous. Momentum, volatility and position
size are answerable exactly — so those are what it gives, and it says so.

---

## 2f. Knowing things — the library (new)

| You say | What ARC gives | Needs |
|---|---|---|
| **"how many states in india"** | 28 states and 8 union territories, with the 2019 reorganisation note and a source | **Lite** |
| **"how tall is everest"** | 8,848.86 m, agreed by Nepal and China in 2020 | Lite |
| "what is a qubit" / "what is cpr" / "what is a byte" | the shelf answer + its source and year | Lite |
| **"what do you know"** | the shelf: 75 facts across india · world · science · tech · money · health · food · myths, plus how many chunks of *your* files are indexed | Lite |
| "what do you know about tech" | the 13 tech entries, one line each | Lite |
| **"tell me a fact"** | a random entry, cited | Lite |
| **"index my notes folder"** | reads that folder (txt/md/csv/json/pdf…) and makes it searchable — nothing is copied or changed | Lite |
| "what is the rooftop cafe called" (after indexing) | **quotes the sentence from your notes file** — quoted, never paraphrased into a claim | Lite |
| **"fetch Vikram Sarabhai"** / "look up Hampi" | Wikipedia summary with the URL and the date it was read, cached a week | Internet |
| **"who won the 2024 election"** / "gold price today" | *"I do not know that one, and I will not improvise it"* + a real search link | Lite |

The rule behind the whole section: four sources only — the shelf, your files, a live
lookup, and the machine's own measurements. Outside those four, ARC says it does not
know. It never fills the gap from memory.

---

## 2g. The studio — video, audio, images (new)

Say the file name and the verb; ARC picks the right studio tool.

| You say | What ARC gives | Needs |
|---|---|---|
| **"make a reel from a.mp4 and b.mp4 titled Belagavi Sunrise"** | 9:16 reel, cross-fade between clips, cinematic grade, the title burned in, music ducked under the voice | ffmpeg |
| "make a story from clip1.mp4" | 9:16, 15 s template, warm grade, gentle fades | ffmpeg |
| "make a teaser from a.mp4 b.mp4" | 21:9 letterboxed, noir, hard cuts | ffmpeg |
| "make a slideshow from photo1.jpg photo2.jpg" | stills with a slow ken-burns push | ffmpeg |
| **"put a cinematic look on clip.mp4"** | graded copy; `noir`, `teal_orange`, `vintage`, `cyberpunk`, `vhs`, `dream`, `grain`, `vignette`, `slowmo`, `letterbox` | ffmpeg |
| **"remove background noise from voice.wav"** | spectral denoise + 80 Hz high-pass, length preserved | ffmpeg |
| "make the podcast louder voice.wav" | `loudnorm` to **-16 LUFS** (social = -14) | ffmpeg |
| "apply noir grade to photo.jpg" | graded sibling file, originals untouched | Pillow |
| **"make an instagram post from photo.jpg"** | 1080×1080 card with scrim + title + subtitle | Pillow |
| "instagram story card from photo.jpg" / "youtube thumbnail from photo.jpg" | 1080×1920 / 1280×720 | Pillow |
| **"collage photo1.jpg photo2.jpg"** | grid collage, cells measured, no repeats | Pillow |
| "grade all photos in C:\\Users\\me\\Pictures\\Goa" | every image graded to new sibling files | Pillow |
| "mix voice.wav and music.wav under the voice" | two-track mix, music sidechain-ducked under speech | ffmpeg |
| "waveform of voice.wav" | 1200×300 PNG you can drop on a video | ffmpeg |
| "where does the speech start in voice.wav" | silence-detected timecodes — measured, not guessed | ffmpeg |
| **"what video templates do you have"** | the full catalogue: 10 templates, 26 transitions, 17 looks with their names | none |

Two honest limits: **captions are never invented** (supply an `.srt`), and **music is
never synthesised** (supply the file — missing path is a refusal, not a placeholder).

---

## 2i. Opening and closing by voice (new)

| You say / do | What happens | Needs |
|---|---|---|
| **"hey jarvis"** (app closed, launcher armed) | the launcher starts the app and hands the microphone over | voice extras |
| **"hey jarvis"** (app in the tray or hidden) | the window comes to the front and magic mode begins | voice extras |
| **"bye jarvis"** | wallpaper restored → **the app closes** (default). Settings → *On "BYE JARVIS"* can make it close-and-leave-nothing, or just hide | voice extras |
| `python tools\voice_roundtrip.py` | proves the whole open/close decision path with the real app and the real socket, no microphone | nothing |
| `python tools\crosscheck.py` | every designed feature: present / proven / failed / cannot-prove-here | nothing (~90 s) |
| `Ctrl+Alt+Q` | always quits everything, including the voice daemon | nothing |

**Why a launcher process exists:** if the app ends and nothing is listening, "hey jarvis"
can never bring it back. So before closing, Arc Desk starts a small launcher and waits 1.5 s
to confirm it is still alive. If it is not, **the app stays open and says why** instead of
closing into silence.

---

## 2h. Building, checking, and the tool list (new)

These are the commands behind the claims. All free, all offline, none of them change
anything on your machine.

| Command | What it does | Takes |
|---|---|---|
| `python tools\packaging.py` | can this be built and uninstalled safely? 35 checks: spec, entry points, bundled pages, icon, installer, uninstaller, batch paths. Three rows print `UNVERIFIED` because a Windows build machine is required — that is the honest state, not a failure | ~0.3 s |
| `python tools\gen_tools_doc.py` | rebuild `TOOLS.md` + `arcdesk/TOOLS_PAGE.html` from the registry | ~0.4 s |
| `python tools\gen_tools_doc.py --check` | exit 1 if either file is stale (runs inside `check.bat`) | ~0.4 s |
| `python tools\smoke_firstrun.py --shadow` | boot the real app, prove it wrote its settings, ask it to close, require exit 0. Add `--no-instance` to run next to a running copy | ~8 s |
| `python tools\make_icon.py` | redraw `shots/arc_icon.png` + `.ico` (7 sizes) | ~1.5 s |
| `check.bat` | **nine** steps: voice close → boot smoke → tests → doctor → Windows-untouched scan → GitHub stack → capability probe → packaging → tool-list freshness | ~2 min |
| right-click the reactor → **What can I ask? (all of it)** | the same list as a searchable page in your browser, offline | instant |
| `python tools\speedcheck.py` | measured answer speed: Lite, routing, a tool call, a vault save | ~2 s |
| `python tools\sizecheck.py --compress` | what is big, and what lzma2 actually makes of it (measured) | ~90 s |
| `packaging\fetch_runtime.py` | fetches ffmpeg + node for the installer (build machine only) | first run only |
| `packaging\build_all.bat` | **one command → `dist\ArcDeskSetup.exe`** | ~10 min |

`TOOLS.md` is generated, never edited by hand — 88 tools, their arguments, which ones ask
before acting (7), and which are read-only (79). If it disagrees with the code, `check.bat`
fails.

---

## 2j. The vault — where your work is saved (new)

| You say | What happens |
|---|---|
| "start a project called Belagavi cafe site" | creates the project folder and makes it current |
| "save this: homepage copy is done" | appends to that project's `%APPDATA%\ArcDesk\vault\...\notes.md` |
| "where do my files save?" | the exact folder path + project count and size |
| "export this project to my desktop" | a new `ArcVault-<name>-<timestamp>` folder, **size-verified**, on your Desktop (or Documents / Downloads / `D:\anything`) |
| "what was i doing?" | the last few checkpoints and the last notes line |
| "add C:\Users\me\brief.docx to this project" | **copies** it in; your original is untouched |
| "list my projects" | every project, newest first |

Every answer is appended to the open project automatically (0.45 ms). Settings → Vault
moves the whole vault to another drive, including a pen drive.

---

## 3. What it will refuse, and why

| You say | What ARC says |
|---|---|
| "draw a dragon" | lists the 10 subjects it can draw; does not invent one |
| "make it photorealistic" | offers the local image-model path (ComfyUI etc.) |
| "answer this web page" | says `web_search` only opens a tab — unless Fetch MCP is enabled |
| "describe this photo" | `look` only reads text — it says it cannot describe pictures |
| **"summarise this mp3"** | gives duration/codec and says the words need `faster-whisper`; it will not invent a transcript |
| **"how much paracetamol should I take"** | the printed label range + a pharmacist; never a dose for you |
| "what is this medicine (one it does not know)" | *"I do not have verified information for that, and I will not guess"* |
| **"should i buy reliance"** | measurements and position maths, explicitly not advice |
| "what price will it be tomorrow" | a line through past prices with an error band, labelled as a line through the past |
| anything while a paid brain is configured | refuses before the request, answers with Lite |

---

## 4. Voice notes

- Wake word is **off by default** and needs `vosk` or `openwakeword` (`install_voice.bat`).
- Speak, then pause: the command window is 7 s by default.
- Want to see *how* a phrase is understood, stage by stage?
  `python tools\explain.py "hey jarvis draw an elephant" --run --then "hey jarvis make it purple"`
  ([`WAKE.md`](WAKE.md) has the five-stage table), and
  `python tools\think.py "draw me a cat"` traces how the request is reasoned about and
  where the answer appears.
- Want to hear the output path or test it offline? `python tools\say.py --dry`,
  `python tools\say.py --cancel`, `python tools\say.py "text" --wav out.wav`.
- Running a real local model? `python tools\live.py --repeat 3` prints every round, the
  token counts and whether the model actually called a tool. `--core` sends the 18-tool
  spoken subset instead of the routed eight.
- **"stop" / "shut up" / "chup" / "niru"** silences the voice mid-sentence, and so does `Esc`
  in the window. Interrupting never leaves half a sentence playing.
- No microphone? Everything above works **typed** — the console (`Ctrl+J`), the palette
  (`Ctrl+Alt+J`), the easel's text line, and `python run.py --ask "draw an elephant"`.

---

## 5. Related docs

`MCP.md` — the nine extra tool servers, verified working (65 tools).
`CAPABILITIES.md` — the measured inventory: latency, memory, what fails.
`tests/test_art.py` — the drawing engine is tested; `tests/test_mcp_presets.py` guards MCP.
