# Arc Desk — build plan

Cost of software: **₹0**. Everything below runs on free tools. The only paid things later
are optional (weather API is free, AI API is optional and pay-per-use).

The order is deliberate: each phase must keep the performance budget from `PERFORMANCE.md`
before the next one starts.

---

## Phase 1 — ARC Control Center ✅ (this build)

One window, futuristic dashboard, clock, CPU/RAM, power modes, shortcuts, tray, autostart,
optional weather, settings persistence, self-measuring footprint.

**Budget spent:** ~72 MB RAM, 2–5 % of one core.
**Stack decision:** PySide6 **Widgets + QPainter**, *not* Qt Quick/QML. The QML engine alone
would add 35–50 MB of baseline RAM before drawing a single frame. If Phase 3 needs a live 3D
layer, that is the moment to evaluate a small QML or OpenGL surface — not before.

**Test checklist before Phase 2:**
- [ ] boots on your Windows build, no console window (`start_arcdesk.vbs`)
- [ ] all four modes look right and persist after restart
- [ ] Task Manager: memory flat after 30 minutes, CPU under 6 %
- [ ] move / close / tray restore / quit all behave
- [ ] shortcut tiles launch the right apps

---

## Phase 2 — Assistant, companion, wake word ✅ (this build)

Console, 88 tools, Lite brain, LLM brain (5 providers), OS-native voice in/out, painted
companion, offline "Hey JARVIS" wake word with a custom phrase, running in its own process.
Backend engines are open-source libraries only — see `CREDITS.md`.

Also shipped: normal-boot mode (Windows untouched, hidden app), global hotkeys, command
palette, awakening cinematic, and the Windows-untouched audit (`tools/desktop_check.py`).

Still open from this phase:
- [ ] wake phrase editable from the UI (today: `settings.json`)
- [ ] freeze `arc_daemon.py` separately so a packaged .exe can use voice
- [ ] floating HUD panels (small always-on-top clock / stats windows)

## Phase 2b — Floating HUD

**2a. Companion (offline first).**
A small painted robot in the corner: idle bob, blink, look-at-mouse, 3 click actions.
Same rules — sprite layers cached, one ticker, ~0 extra RAM. This is a *state machine +
cached frames*, not a physics sim.

**2b. Floating HUD panels.**
Transparent, frameless, always-on-top mini panels (clock only, stats only). Each one is a
tiny window that reuses the same ticker; closed by default so the desktop starts clean.

**2c. Optional AI (off by default).**
The companion's "ask" action, if you switch it on, sends one request from a worker thread to
a hosted model and speaks the reply. Keep it opt-in: no key, no network, no cost otherwise.

**Budget gate:** total RAM ≤ 95 MB, CPU ≤ 7 % at 30 fps.

---

## Phase 3 — Gravity Charms ✅ (this build)

Floating robot / planet / car / butterfly / reactor charms on the desktop, in one transparent
click-through overlay: drag, wheel-resize, per-charm speed and kind, positions persisted,
right-click menu, add/remove, hidden in Gaming mode, 20 fps cap, 8-charm limit.
Also shipped: the single settings window (voice, wake phrase, boot, hotkeys, charms, weather).

Still open from this phase:
- [ ] charm packs / user-provided PNG sprites
- [ ] multi-monitor placement UI (currently clamped to the combined screen area)
- [ ] per-charm "always on this monitor" pinning

## Phase 3c — Magic mode ✅ (this build)

"Hey JARVIS" → fullscreen ARC workspace + wallpaper swap; "BYE JARVIS" → restored. Journaled
two-phase change so a crash cannot leave the desktop modified. Explicitly refuses shell
replacement (Explorer/`Shell=` registry), which is the part that would actually break Windows.

Still open:
- [ ] per-monitor wallpaper (Windows 11 spans one wallpaper across all displays by default)
- [ ] magic mode themes (a second look for gaming / night)
- [ ] optional "arc ring" cursor pack inside magic mode only

## Phase 3b — 3D Universe (original plan, still optional)

This is the phase that can wreck the laptop if done carelessly, so it gets its own rules:

- **Separate transparent overlay window**, not a rework of the main window.
- Objects are **2D sprites with a 3D-ish animation**, not real meshes, for v1. A ~2 KB
  painted sprite per charm, drawn by Qt, costs almost nothing.
- A real Three.js/WebGL layer means embedding WebEngine (100 MB+) — **only** do that if you
  truly need free-rotating 3D, and then run it in its own process you can kill.
- Charm count capped (default 8), animated at 20 fps, paused when a fullscreen app runs.
- Drag / resize / speed per charm, positions saved to settings.

**Budget gate:** overlay adds ≤ 25 MB, ≤ 3 % CPU with 8 charms.

---

## Phase 3d — Open-source ecosystem ✅ (this build)

Nine local open-source backends auto-detected over localhost, plus an MCP client so any
open-source tool server from GitHub becomes ARC's hands (`files`, `git`, `sqlite`, `fetch`,
`memory`, …). Nothing bundled, nothing auto-installed, nothing copied — see `OPEN_SOURCE.md`.

Still open:
- [ ] one-click "start Ollama" button that launches the backend if it is installed
- [ ] MCP server presets with a trust prompt before first run
- [ ] per-tool permission rules (allow `files:read`, ask for `files:write`)

## Phase 4 — Smart modes, polish, ship

- Mode actions become real: Focus hides panels and mutes notifications, Chill starts
  ambience (optional looping audio, user-supplied file), Gaming pauses every effect,
  Night dims and slows animation.
- Startup launch, safe exit, crash-safe settings (already atomic).
- Packaging: PyInstaller folder build (~45–60 MB), optional code-signing later.
- Optional: Nuitka build for a smaller, faster native binary if size becomes a problem.

---

## Realistic effort

| Phase | Evenings (2–3 h) | Notes |
|---|---|---|
| 1 | done | core is in place |
| 2 | 4–6 | companion art is the long part |
| 3 | 8–12 | overlay + interaction, most risk |
| 4 | 3–5 | polish, packaging, testing |

## Risks worth naming

| Risk | Mitigation |
|---|---|
| Effects eat GPU while gaming | automatic 10 fps fullscreen guard (already shipped) |
| Transparent overlay clicks block the desktop | click-through flag by default, toggle to edit |
| AI feature turns into a subscription | stay opt-in, offline companion works without it |
| Feature creep kills the budget | every phase has a RAM/CPU gate before the next starts |

## Phase 18 — proved on Windows ✅ (this build)

- The first CI run on GitHub's Windows runner went red and taught the project five things
  Linux could not: platform-default decoding in the test runner and six test files, a
  192-second sparse-file test, WAV import demanding ffmpeg, an absolute frame budget that
  penalised a slow runner, and a smoke test reading an exit code a windowed exe never
  sets. All fixed; audit section F keeps them fixed.

## Phase 17 — audited, not asserted ✅ (this build)

- **`tests/test_audit.py`**: Settings wired both ways, 88 tools valid, defaults on/off with
  a reason each, the four-mode metaphor, all modules import.
- **two dead things fixed**: `effects` was a stored setting nothing read (now a live
  "Visual effects" control that measurably changes the frame cost); the backup space
  guard refused a 400 KB copy on a 200 MB-free drive (now refuses only when it truly
  does not fit).
- **62 tests, 88 tools, crosscheck 54 proven / 0 failed.**

## Phase 16 — how it opens, and teaching it your voice in the app ✅ (this build)

- **one question at setup**: desktop icon vs voice, implemented as `firstrun.set_mode()`
  (two flags, one answer), asked in the setup card and again in Settings, honoured
  immediately in the same session.
- **in-app enrolment** (`widgets/voicelock.py`): three 4-second takes, live level,
  failure messages, WAV fallback, agreement score, lock switch.
- **installer**: the same question in `[Tasks]`, plus an opt-out post-install download of
  the two speech models (70 MB) so "hey jarvis" works on a fresh laptop.
- **real-model bug fixed**: sherpa-onnx renamed the embedding call; same voice verified at
  0.70–0.80 and a different voice at 0.03–0.16.
- **2 new tests** → 61 tests
- **the bundle was built and launched for real** (298.5 MB → 86.4 MB packed, 51 s), which
  exposed three packaging bugs the tests could not see; `build_all.sh` + a Windows CI
  workflow now make the installer reproducible without a Windows PC in the room.

## Phase 15 — carry it, and lock it to the new person ✅ (this build)

- **`tools/move.py`** — pack/unpack the right data (vault, clone clip, settings without
  keys), exclude the wrong data (voice fingerprints, models, logs), refuse silent
  overwrites, recursive `--merge`.
- **config fix**: settings path resolved per call, not frozen at import — portable mode
  and the multi-machine path both depend on it.
- **`MOVE.md`** — new laptop in four commands; the .exe still comes from Windows.
- **1 new test** → 61 tests

## Phase 14 — three languages, measured clips ✅ (this build)

- **scope contract**: `clone.PROMISED` = Tamil → IndicF5, Hindi → IndicF5,
  English → XTTS. Everything else is a documented bonus (`test_clean.py` pins it).
- **`clone.analyse()`**: SNR, background, clipping, quiet-frame ratio → grade + advice;
  reads MP3/M4A/MP4 through ffmpeg.
- **`tools/clean_voice.py`**: two-pass denoise/trim/normalise, before/after SNR printed,
  optional `--demucs` for music, `--import` in one command.
  Measured on a 50 Hz-hum clip: **12.2 → 20.6 dB**.
- **1 new test** → 61 tests

## Phase 13 — your voice, and only yours ✅ (this build)

- **new** `arcdesk/clone.py` — reference import (VAD trim, stitching for edited clips,
  loudness normalisation, 24 kHz mono, transcript), and language→engine routing:
  IndicF5 for 11 Indic languages, XTTS for 17 others, Piper/SAPI as honest fallbacks.
  Tamil is never handed to an engine that cannot pronounce it.
- **new** `arcdesk/voiceid.py` — speaker verification from 3 clips, per-machine
  profiles stored as vectors (not audio), self-similarity sets each profile's own
  threshold, multiple people per machine, and a refusal to pretend when no model exists.
- **daemon** `--voice-lock` gate on the *command* audio; speech chain clone → piper → SAPI.
- **new CLI + installer** `tools/voice_setup.py`, `install_clone.bat` (sizes printed,
  nothing downloaded silently).
- **2 new tests** (`test_clone.py`, `test_voiceid.py`) → 61 tests

## Phase 12 — a real photograph, honestly ✅ (this build)

The user compared a sketch to a real elephant and was right: they are not the same thing.
`draw` was never going to fix that.

- **new** `arcdesk/photo.py` — Wikimedia Commons search + download, free licences only,
  photographer/licence/source printed on every result, CC0 preferred.
- **new tool** `photo` (88 tools), `host.request_photo` → the easel shows the photograph and
  clears the sketch so "make it purple" cannot pretend to edit it.
- **refuses**: non-image downloads, files over 12 MB, overwriting an earlier picture;
  offline is a sentence, not a traceback.
- **Lite routing** for `real photo of …`, `picture of …`, `… photo`, and Tamil/Hindi animal
  names; generation and sketching keep their own paths.
- **1 new test** (`test_photo.py`, fully offline) → 61 tests

## Phase 11 — the vault, the speed, one double-click ✅ (this build)

Four asks in one message; each one is now a file you can point at.

- **new** `arcdesk/vault.py` — projects as plain folders (`%APPDATA%\ArcDesk\vault\...\project.json`, `%APPDATA%\ArcDesk\vault\...\notes.md`,
  `%APPDATA%\ArcDesk\vault\...\progress.jsonl`, `files/`). Every answer is appended automatically (0.45 ms). Export
  copies out to Desktop / any drive as a new size-verified folder; adding a file copies it
  and never touches the original; moving the vault to another drive is one setting.
- **new tool** `vault` (88 tools now) + Lite intents for "start a project",
  "save this", "where do my files save", "export this to my desktop", "what was I doing".
- **speed, measured** (`tools/speedcheck.py`): Lite **0.28 ms** p50 · routing **1.01 ms**
  (was 75 ms — token bags are now cached and the sentence is analysed once, not 87 times)
  · tool call 0.01 ms · vault save 0.45 ms.
- **one click** — `packaging/fetch_runtime.py` + `packaging/build_all.bat` +
  a rewritten `packaging\arcdesk.iss`: per-user, no admin, `Components` for media/Node,
  `lzma2/ultra64`, `FinishedLabel` = "installed successfully", uninstall **asks** before
  deleting the vault, and bundled tools go on the app's *process* PATH only.
- **size, measured** (`tools/sizecheck.py --compress`): 195 MB of ffmpeg payload →
  **58 MB (29%)**. The final Setup number is printed by build_all.bat on Windows.
- **bugs fixed**: `find_files` (Lite emitted a tool name that did not exist — "find my
  report" never worked; now there is a static guard over all 79 emitted names) · the
  torn-line loss in `%APPDATA%\ArcDesk\vault\...\progress.jsonl` · `_ears_can_stay()` shadowing its own injected probe.
- **1 new test** (`test_vault.py`) → 61 tests

## Phase 10 — "close" means close ✅ (this build)

The acceptance criterion from day one — *"HEY JARVIS opens it, BYE JARVIS closes it"* — was
half implemented, and the cross-check is what caught it.

- default `bye_action` is now **exit** (it was `hide`), so the process really ends
- "bye jarvis" now works **without** magic mode being active (it used to print a note and do
  nothing)
- `_arm_launcher()` proves a launcher survives 1.5 s **before** quitting; if it does not, the
  app stays open and explains — never quits into silence
- Settings offers three honest choices: close + launcher, close + nothing, hide
- **new** `tools/voice_roundtrip.py` — real app, real protocol, checks the process exit code
- **new** `tools/crosscheck.py` — the whole design in one table; `--write` saves
  `CROSSCHECK.md`. Run: **15 present · 42 proven · 0 failed · 4 cannot-prove-here**
- **1 new test** (`test_voice_close.py`) and a new safety-net case in `test_app_lifecycle.py`
  → 61 tests
- the packaging folder had to move from `build/` to `packaging/`: anything named `build` is
  treated as disposable by build tools *and* by this workspace's snapshots, which is how the
  spec went missing once

## Phase 9 — make the claims true ✅ (this build)

No new capability. This phase exists because the previous eight phases had shipped
documentation for things that were not there, and a doc you cannot check is a lie with good
formatting.

- **the missing build** — `packaging/arcdesk.spec` (two `EXE`s: the window and the ears),
  `packaging/build.bat` (five steps, stops at the first failure), `packaging/arcdesk.iss`
  (per-user, no UAC, no service, asks before deleting notes), `packaging/make_installer.bat`
- **new** `tools/packaging.py` — 35 checks with no Windows machine: spec parses and uses
  `collect_submodules`, both entry points are named, the installer never asks for admin,
  every `Source:` line resolves, the batch files reference real paths, `uninstall.bat` never
  blanket-kills Python, and `check.bat` runs the steps that matter. Four rows are printed as
  **UNVERIFIED** on purpose — PyInstaller cannot cross-compile, so "the exe launches" is not
  something this repo is allowed to claim.
- **new** `tools/gen_tools_doc.py` — `TOOLS.md` and a searchable, offline `arcdesk/TOOLS_PAGE.html`
  generated from `tools.TOOLS`. The category table is exhaustive by contract: an
  uncategorised tool fails the generator instead of landing in "misc".
- **new** `tools/smoke_firstrun.py` + `tests/test_firstrun.py` — boots the real entry point,
  proves settings were written, sends a stop signal, requires exit 0.
- **new** `tools/make_icon.py` — original icon, 7 sizes, drawn not downloaded.
- **three real bugs found by doing this**: the pages were bundled from the wrong folder;
  `uninstall.bat` killed every Python GUI on the machine; and a stop signal during first run
  could not be answered (nested `dlg.exec()`), then crashed the interpreter when answered.
- **2 new tests** (`test_packaging.py`, `test_firstrun.py`) → 50 total

## Phase 8 — backup, autostart, first run ✅ (this build)

The three things that make it feel like software rather than a repository — and the
first feature in this project that can protect a file instead of only reading one.

- **new** `arcdesk/backup.py` — copy + **SHA-256 verify on the destination**, one hash
  pass while copying, a manifest per run, a new `ArcBackup-<timestamp>` folder every time,
  and hard refusals: into-itself, source-inside-target, drive root, missing path, and
  "not enough room" *before* a byte is written. Originals are opened read-only; a test
  snapshots every mtime to prove it. `verify()` re-checks an old backup by name.
- **new** `arcdesk/autostart.py` — one `HKCU` Run value, read back after writing; `stale`
  reported when the install moved; off unless asked; also implements freedesktop
  autostart and a macOS LaunchAgent, because that is what the tests can actually run
- **new** `arcdesk/firstrun.py` — the wizard's logic, outside the dialog: five decisions
  with their costs, applied in one place, so the voice command "start with windows" and
  the checkbox cannot drift apart
- **new** `arcdesk/docs_worker.py` — document indexing in one background thread, with a
  status string and a console note, so a 4,000-PDF folder never freezes the window
- **tray/quick menu**: Back up my files · Why is this PC slow · Index my documents ·
  Start with Windows (checkable, all platforms) — the last one was previously guarded by
  `os.name == "nt"` and would have raised `ImportError` on Windows had `autostart` been
  missing; it now has a stable API surface (`is_enabled` / `set_enabled` / `status`)
- **`tools/doctor.py --deep` v2** — now prints the environment (python, ffmpeg, tesseract,
  players, psutil, RAM, CPUs) and runs **12 core checks** of the last four waves *before*
  the desktop tools: media index, playback, document search, error reader, slowdown
  diagnosis, backup+verify, autostart read-only, and the crisis path. One log file.
- **2 new tools** (`backup` guarded, `autostart`); probe: **88 tools · 65 live · 0 failed**
- **new** `tests/test_backup.py` — 60 checks: verified copy, tamper detection, no-merge on
  a second run, source mtimes unchanged, five refusal shapes, autostart enable/disable
  round trip, the wizard applying exactly four answers, and the background indexer

## Phase 7 — "yen slow da?" ✅ (this build)

`system_report` prints numbers. Nobody has ever been helped by numbers. This turns them
into a cause and a next step — and refuses to do so without evidence.

- **new** `arcdesk/pchealth.py` — 11 rules over **two samples one second apart**: RAM
  pressure, pagefile thrash, a named CPU hog, whole-CPU load, nearly-full drive, disk
  throughput saturation, startup bloat, process count, battery-under-load, thermal
  throttling, long uptime (labelled a heuristic, because that is what it is)
- every finding quotes the measurement that fired it, is graded **high / medium / note**,
  and carries ordered fixes — plus what ARC itself can and will not do
- honest edges: no temperature sensor → "I cannot see it", never "it is cool"; no psutil →
  no numbers at all; **nothing is killed, closed, or changed** — the suggested
  `close_app` was already `confirm=True`
- **new tool** `pc_health`; probe: **88 tools · 65 live · 0 failed**
- **new** `tests/test_pchealth.py` — `diagnose()` is pure over a sample dict, so the rules
  are proven against **synthetic machines** (96% RAM, one 78% CPU process, 2.6% free disk,
  91.5 °C, 19 startup entries, a healthy one) instead of waiting for a real laptop to be slow

## Phase 6 — the words inside the files ✅ (this build)

The file index could answer *"where is budget.xlsx?"*. It could not answer the question
people actually ask: *"which of my files mentions the Hampi advance?"*

- **new** `arcdesk/deepsearch.py` — content index over Word, Excel, PowerPoint, PDF, CSV
  and text, reusing `reading.py` (one extractor, not two)
- every hit is **evidence**: file, type, size, **line number**, the sentence around the
  match, and the full path — so a hit can be checked in one glance, not trusted blindly
- **incremental by size + mtime**, including the files that have *no* text: 4 documents
  index in 14 ms, the second pass re-reads 0 files in 0.3 ms. A 50 MB scanned PDF is not
  re-read on every run
- honest edges: a scan with no text layer is named in the reply rather than counted as an
  empty file, partial matches say so in the first line, and a miss never returns a guess
- **new tool** `search_inside`; probe: **88 tools · 65 live · 0 failed**
- **new** `tests/test_inside.py` — a folder built like a real one (`node_modules`, an empty
  file, a binary, a docx, an xlsx, a csv): read-only proven by snapshotting every mtime,
  ranking proven (all-words beats some-words), incremental proven (reread 0 then 1 after an
  edit), and forgetting proven to delete the index and not the documents

## Phase 5b — the error reader ✅ (this build)

*"idhu enna error da"* is the most frequent real request a companion gets, and the most
dangerous one to answer badly: a hallucinated fix at midnight costs someone their files.

- **new** `arcdesk/screenhelp.py` — 24 hand-written error families (Windows codes, BSOD stop
  codes, SmartScreen, services, Windows Update, Python, git, DNS/refused/404/TLS/offline,
  ffmpeg, locked files, corrupt documents, no audio, unreadable USB), each with means → why
  → ordered steps → what ARC can and cannot do → a **certain / likely** class
- **new tool** `explain` — text, clipboard, or a screenshot + OCR through the existing
  `vision.py`; probe: **88 tools · 65 live · 0 failed**
- the honesty rails are the feature: it **quotes the line it read** before explaining it,
  refuses to invent a cause for an unrecognised message, believes "0 errors", and does not
  diagnose a photograph
- **new** `tools/sandbox_env.sh` — one command restores the *verification* toolchain
  (ffmpeg/ffplay, Tesseract, Qt libs, `uvx`) in a rootless sandbox with no system-wide
  install, because a red board caused by a missing binary is a board that lies
- **new** `tests/test_screenhelp.py` — 24 real message wordings (typos and OCR warts
  included) named correctly, specific signatures ranked above generic ones, and the
  refusal paths: unknown text, "0 errors", a wallpaper, an empty screen, missing Tesseract

## Phase 5 — play, scan, think, mentor ✅ (this build)

> The request: *"songs play pana sonna play aganum ... external hard disk ah scan pana sonnalum
> pananum ... rendering, output varathuku romba time aaga koodathu ... mentor ah, guide panra
> wellwisher ah, oru analyst ah ... emotions ah value panra mathiri"*

- **new** `arcdesk/library.py` — a read-only media index: every fixed and removable drive,
  `MAX_FILES` 60k, depth 9, a 900 s cache, and phrase → token → fuzzy scoring.
  An unplugged path is an **error that keeps the old index**, not a silent rescan
- **new** `arcdesk/player.py` — mpv → vlc → ffplay → mplayer → OS handler, a real process,
  measured time-to-start, `killpg` on stop. A player that dies inside 350 ms is a failure with
  its stderr, not silence
- **new** `arcdesk/planner.py` — deterministic think → plan → run, six steps maximum
- **new** `arcdesk/coach.py` — listen · mentor · analyst · decide · plan · check-in ·
  journal · reflection, with crisis rails (Tele-MANAS 14416, KIRAN, 112, 988, 116 123)
- **4 new tools** — `play`, `library`, `plan`, `coach`; probe run: **88 tools · 65 live ·
  6 guarded · 0 failed**
- flaws found and fixed: the planner played a literal *"scan my external disk and play nee
  paartha"* as a song title; "play next song" was hijacked away from the media keys; a file
  question containing `.xlsx` was answered from the facts library; a scan of an unplugged
  drive quietly replaced a good index with the default folders

## Phase 4b — full-code audit ✅

Every file and every claim checked, then the gaps filled:

- `pyflakes` over the whole project: **0 findings** (was 24, all unused imports)
- `tests/test_docs.py` — every count in the docs must equal the code, every file a doc
  points at must exist, no money language may creep back
- **new** `tests/run_all.py` + `check.bat` — one command validates everything
  (GUI tests used to go silent without the offscreen flag, which is worse than failing)
- `tests/test_system.py` — settings isolation, crash log + key scrubbing, single instance,
  doctor, summon signal
- `tests/test_free_guard.py` — a paid brain is refused before any request; the agent falls
  back to Lite and still answers
- `tests/test_reminders.py` / `test_focus.py` / `test_search.py` / `test_briefing.py` — the day layer: one announcement per reminder, real elapsed focus time, a read-only file index that never writes to your folders, and a briefing that admits when it has no psutil
- `tests/test_business.py` — content, marketing, strategy and hotel maths recomputed by hand (a break-even 20% off changes whether someone signs a lease)
- `tests/test_travel_craft.py` — haversine distances, real map links, contrast ratios, reproducible kolam seeds, SVG well-formedness
- `tests/test_mind.py` — mining states its n, mentoring asks instead of answering, forecasting labels arithmetic as arithmetic, security refuses intrusion in code
- `tests/test_backup.py` — verified backup, five refusal shapes, autostart round trip, wizard round trip
- `tests/test_pchealth.py` — 11 slowdown rules proven against synthetic machines, plus the honest-sensor and no-psutil paths
- `tests/test_inside.py` — content search with receipts: line numbers, read-only proof, incremental re-index
- `tests/test_screenhelp.py` — 24 real error messages, the ranking rules, and every refusal path
- `tests/test_playback.py` — a throw-away library with the junk real folders contain (track numbers, `(Official Video)`, `[320kbps]`, a 500-byte ringtone, a system folder): the index keeps the three songs and the video, strips the noise, ignores the stubs, finds "ilaiya nila" by typo, searches 20,000 rows in under 120 ms, plays through ffplay with a measured start, stops on command, and a miss is a sentence with a next step instead of a wrong file
- `tests/test_coach.py` — a crisis message gets Tele-MANAS 14416 and KIRAN 1800-599-0019 and never a diagnosis; a heavy day is heard before it is solved; the mentor labels itself a framework; the analyst separates supplied numbers from guesses; the decision frame asks what is reversible; the journal counts only entries that exist
- `tests/test_media.py` — the studio's output is *measured*: a story is 1080×1920, a 2 s + 1.5 s pair with a 0.6 s cross-fade is 2.93 s, noir is genuinely monochrome, a vignette darkens corners but not the centre, batch grading leaves every original's mtime untouched, and an impossible template is refused with the list of real ones
- `tests/test_world.py` — the library's four rules: every entry carries a source and a year; a drifting number is always quoted with its year; a live question returns "I do not know" *plus* a link; an indexed file is quoted by name
- `tests/test_packages.py` — the catalogue answers in-app: right project first, no substring traps, and the four phrasings that reach it
- `tests/test_catalog.py` — 86 packages, every brain classified ₹0, refusals documented
- **new** `arcdesk/logs.py` — rotating crash log with key scrubbing (a packaged exe has no
  console, so this was the difference between reportable and invisible)
- **new** `arcdesk/instance.py` — one Arc Desk at a time; a second launch summons the first
- **new** `tools/doctor.py` + `run.py --doctor` + Settings → System → Run doctor
- **new** `ARCDESK_HOME` portable mode, also used by every test so they cannot pollute real
  settings (that bug was live: the test suite had been writing `bye_action=exit` into the
  user's own settings file)
- docs drift fixed across the tree: the tool count and the engine count now match the
  code in every file, and README is no longer titled Phase 1

## Phase 4c — capability audit ✅ (this build)

Instead of describing what ARC does, it was measured:

- **new** `tools/capability.py` — probes all 88 tools; 57 executed live, 6 confirmed guarded,
  0 raised. Every other row says why it was skipped
- **new** `CAPABILITIES.md` — actions, reactions, skills, capacity numbers, known limits
- **new** `tests/test_lite_intents.py` — 32 real phrases; Lite went **86% → 100%**
- flaws fixed: `find_file` raised `TypeError` in Lite (unreachable branch), no offline
  `close_app` intent, "what is eating my ram" answered with the wrong tool, and a docstring
  that claimed OS gating the code did not have
- `check.bat` is now 5 steps: tests → doctor → Windows check → stack scan → capability probe

## Phase 4d — MCP enabled + ARC Sketch ✅ (this build)

> **Current status, re-evaluated 22 Oct 2026:** see [`REEVAL.md`](REEVAL.md) — what runs, what has
> never been run (wake word on real hardware, 13 desktop tools), and the ranked next steps.

- **MCP, for real**: `arcdesk/ai/mcp_presets.py` — 9 presets, "Add all free servers" button,
  runners checked before enabling. Measured: **7/7 servers up, 65 MCP tools**, which is 91 in total
  with the built-ins
- bug found and killed: fetch/time/git were pointed at npm packages that do not exist (or are
  npm security placeholders). They are Python servers → `uvx`. Now enforced by test
- **ARC Sketch**: `arcdesk/art.py` + `widgets/artview.py` + tools `draw` and `art_edit`.
  "draw an elephant" produces a vector elephant in ~3 ms, offline; "make it purple and bigger,
  add a sun" edits the document and re-renders; the easel window takes the same edits by typing
- bugs found and killed: `draw an elephant` parsed as article-only (subject lost);
  "make it purple, add a sun" replaced the elephant with a sun; decorations moved with the
  subject; saving twice in one second overwrote the same file
- new tests: `test_art.py` (6 checks) and `test_mcp_presets.py` (6 checks)
- new docs: `COMMANDS.md` (every phrase → what it does), `MCP.md` (the presets, verified)

## Phase 4e — the hologram deck ✅ (this build)

The ask: *"hologram mathiri irukanum, realistic ah, scientific technology server run aana
yepadi irukumo appadi oru view"* — a projection surface that looks like a real instrument,
not a wallpaper with a glowing circle on it.

- **one renderer, two homes**: `arcdesk/widgets/holo.py` — `HoloDeck` paints the surface,
  `HoloWindow` is the standalone fullscreen host, and `MagicScreen` embeds the same pixels
  through `paint_onto(..., compact=True)` so the app buttons and input sit on top of it
- **the look** (rebuilt to match the reference the user supplied): a dotted wireframe
  planet cropped into the left of the frame, a stack of six tilted light rings spiralling
  into a bright core in the middle, a dust field of measured integers behind everything,
  five instrument panes with sparkline traces down the right edge, two amber byte-count
  headlines, a palette block, a marquee of live integers across the top, a 12-second
  telemetry spectrum, per-core load bars, a real log ticker, heavy corner brackets and
  projector grain
- **honesty is enforced, not promised**: every value comes from psutil at 4 Hz or from the
  running app; the build fails if `random()` appears in the telemetry path; the hex gutter
  prints real sample values; `tests/test_holo.py` reads the frame back with the app's own
  OCR to prove the labels are legible
- **measured cost**: 17.9 ms median per frame at 1280×720, 23.5 at 1600×900, 30.4 at
  1920×1080, 39.9 at 4K (renders at 1920 and upscales) on a 2-vCPU software rasteriser — no GPU, no shaders, cached text layers;
  Gaming mode skips the deck entirely
- **bugs found and killed on the way**: a right-aligned gutter column walked leftwards into
  the globe (x mutated per glyph); the ticker drew exactly two copies and overlapped itself;
  the sparklines plotted the deque's zero padding; the spectrum's sine wobble made real data
  wobble; process rows drew under their own bars; headline numbers repeated a value that was
  already printed as a byte count; a `str.replace` on an empty match nearly ate this file
