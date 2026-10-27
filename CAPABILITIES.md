# What ARC can actually do

Measured, not promised. Every number here came from running the code:
`python tools/capability.py --all`, `python tests/run_all.py`, `python tools/bench.py`.

**86 actions · 65 verified live in this run · 6 guarded by design · 0 raised an exception**
+ **65 MCP tools** when the free servers are enabled (7/7 up, measured)

---

## 1. Actions — the 88 tools

`OK` = executed during the probe and returned a usable answer.
`GUARD` = destructive, `confirm=True`, the UI asks before it runs.
`SKIP` = deliberately not executed by the probe (it would open a window, change
your volume, or read your clipboard) — the tool exists and is wired.

| # | Tool | What it really does | Params | Probe |
|---|---|---|---|---|
| 1 | `open_app` | launches a program by name | app | skip |
| 2 | `open_url` | opens a URL in the default browser | url | skip |
| 3 | `web_search` | opens a browser search — **cannot read the results** | query | skip |
| 4 | `system_report` | live CPU, RAM, disk, battery, heaviest process | — | **OK 328 ms** |
| 5 | `running_apps` | top processes by memory | — | **OK 6.5 ms** |
| 6 | `close_app` | terminates a process by name | app | **GUARD** |
| 7 | `set_volume` | 0–100 (pycaw on Windows, amixer/osascript elsewhere) | level | skip |
| 8 | `mute` | toggles system mute | — | skip |
| 9 | `media` | play/pause, next, previous, stop | action | skip |
| 10 | `brightness` | 0–100 | level | skip |
| 11 | `screenshot` | captures the screen to a timestamped PNG | path | **OK 8 ms** |
| 12 | `lock_screen` | locks the session | — | skip |
| 13 | `power` | shutdown / restart / sleep / cancel | action | **GUARD** |
| 14 | `timer` | countdown that notifies when done | minutes, label | **OK** (needs window) |
| 15 | `magic` | enter/leave magic mode | action | **OK** (needs window) |
| 16 | `charms` | show/hide/edit floating charms | action | **OK** (needs window) |
| 17 | `arc_mode` | focus / chill / gaming / night | mode | **OK** (needs window) |
| 18 | `note` | appends to one notes file | text | **OK 0.2 ms** |
| 19 | `read_notes` | reads recent notes back | limit | **OK 0.1 ms** |
| 20 | `find_file` | searches Desktop/Documents/Downloads/Pictures, read-only, 4 s cap | name | **OK 0.2 ms** |
| 21 | `clipboard` | get or set the clipboard | action, text | skip |
| 22 | `weather` | current weather (off by default, needs network) | — | **OK** (honest refusal) |
| 23 | `time` | local time and date | — | **OK 0.0 ms** |
| 24 | `draw` | vector sketch: elephant, cat, dog, house, tree, flower, car, robot, fish, sun | subject, colour, extras | **OK ~3 ms** |
| 25 | `art_edit` | changes the drawing by sentence: colour, size, position, rotation, scenery, undo | instruction | **OK** |
| 26 | `mcp_servers` | lists connected MCP servers | — | **OK** |
| 27 | `windows` | list / focus / minimize / maximize / restore / minimize_all / close a **window** | action, title | **OK** (Linux: says `xdotool` is missing) |
| 28 | `type_text` | types into the focused window — the "open notepad and type X" half | text, delay | **OK** (platform message off-Windows) |
| 29 | `press` | key chords: `enter`, `ctrl+s`, `alt+tab`, `ctrl+shift+t` | keys | **OK** |
| 30 | `file_op` | mkdir / write / append / copy / rename / move, **home folder only**, keeps a `.bak` before overwriting | action, path, target, text | **OK 0.4 ms** |
| 31 | `read_file` | **any format** — pdf, docx, xlsx, pptx, csv/json, image (OCR), audio/video — with `mode=summary\|review\|outline\|text` | path, mode, limit | **OK 20 ms** |
| 32 | `file_delete` | deletes a file inside home (to the trash when one exists) | path | **GUARD** |
| 33 | `run_command` | runs a shell command: blocklisted, confirm-gated, 30 s cap, output capped | command, timeout | **GUARD** |
| 34 | `action_log` | what ARC actually did, from its own journal | limit | **OK 0.1 ms** |
| 35 | `screen_text` | OCR the screen — answers "what does this error say" | lang | **OK** (needs Tesseract) |
| 36 | `click_text` | finds words on screen and clicks them — any app, including games | text, double | **OK on a synthetic screen** |
| 37 | `click_at` | clicks an exact pixel position | x, y, button | **OK** (honest off-desktop) |
| 38 | `ui_controls` | lists the accessible controls of the focused window | limit | **OK** (says when there is no tree) |
| 39 | `ui_act` | click / focus / fill a control by name, falls back to pixels | name, action, value | **OK** |
| 40 | `email_send` | sends through the user's own SMTP account | to, subject, body, attachment | **GUARD** |
| 41 | `email_draft` | opens the mail app with a draft (no password) | to, subject, body | **OK** |
| 42 | `calendar` | adds real `.ics` events, lists the next N days | action, title, when, minutes, days | **OK** |
| 43 | `whatsapp_send` | opens WhatsApp with the message written | number, message | **GUARD** |
| 44 | `calc` | exact arithmetic — `18% of 4500`, `sqrt(144)+2**10` | expression | **OK 0.3 ms** |
| 45 | `convert` | units with kind checking, °C/°F handled properly | value, from_unit, to_unit | **OK** |
| 46 | `rates` | live FX rates (open.er-api.com) | base, symbols | **OK 62 ms** |
| 47 | `stock` | live quote + 30-day move for a ticker or index | symbol | **OK 55 ms** |
| 48 | `project` | straight-line fit through recent prices, ±2σ band | symbol, days | **OK 82 ms** |
| 49 | `market_summary` | NIFTY, SENSEX, gold, USD/INR, BTC in one screen | — | **OK 262 ms** |
| 50 | `teach_macro` | learns a repeatable voice command, safe steps only | instruction | **OK 7 ms** |
| 51 | `macros` | list / run / forget the learned commands | action, name | **OK** |
| 52 | `list_tools` | the whole catalogue, when the routed few are not enough | query | **OK 0.1 ms** |
| 53 | `profile` | what ARC remembers about you (name, editor, city, language) | action, key, value | **OK** |
| 54 | `look` | OCR the screen and answer from what is on it | question, lang | **OK** (needs a display) |
| 55 | `edit_file` | non-destructive edit for every format it can read — always a new timestamped sibling | path, op, + per-format args | **OK 5.5 ms** |
| 56 | `make_media` | image or video from words, free: local A1111/ComfyUI if running, else offline poster / ken-burns clip | prompt, kind, width, height, seconds | **OK 20 ms** |
| 57 | `market` | quote · momentum analysis · position size · watchlist · screener · brief | what, symbol, capital, risk_pct, stop_pct, rule | **OK 62 ms** |
| 58 | `health` | urgency triage · published medicine ranges · anatomy · first aid — no diagnosis, no personal dose | what, query, question | **OK 1 ms** |
| 59 | `holo` | project / dismiss the fullscreen hologram deck | action | skip (needs the window; rendered to `shots/holo_*.png`) |
| 60 | `remind` | timed reminders that speak when they come — add · list · cancel · clear, survive a restart | action, text, which | **OK 0.9 ms** |
| 61 | `focus` | focus (pomodoro) blocks with a real elapsed clock, a local log and a weekly total | action, minutes, label | **OK 0.6 ms** |
| 62 | `briefing` | the morning briefing: clock, calendar, reminders, focus, machine health — only from real sources | what | **OK 8.4 ms** |
| 63 | `packages` | the 86-package GitHub catalogue: search it, detect what is installed, print the install commands | action, query, role, key | **OK 4.1 ms** |
| 64 | `content` | blog/reel/caption/email/ad/product/speech outlines and drafts, hooks, hashtags, posting calendar — word counts measured, no invented engagement numbers | action, topic, kind, tone, audience, weeks | **OK 0.3 ms** |
| 65 | `marketing` | funnel maths (CTR, CPC, CAC, ROAS), UTM builder, SEO/readability of your own text, A/B sample size, channel playbooks | action, impressions…revenue, url, text, baseline | **OK 0.5 ms** |
| 66 | `strategy` | SWOT, Porter's five forces, business model canvas, OKRs, break-even, unit economics, weighted decisions | action, subject, fixed, price, variable, cogs, cac | **OK 0.2 ms** |
| 67 | `hotel` | occupancy · ADR · RevPAR · TRevPAR · GOPPAR, menu costing, SOP checklists, guest journey, rate ladder | action, rooms, sold, room_revenue, costs, items | **OK 0.3 ms** |
| 68 | `travel` | 92 places with coordinates: near-me by haversine, OpenStreetMap links, distances, itineraries, budget bands | action, place, near, radius_km, tag, days, tier | **OK 0.4 ms** |
| 69 | `craft` | colour palettes with measured contrast, printable poster, kolam/rangoli pattern, border strip, monogram — original SVG | action, base, scheme, title, dots, seed | **OK 0.3 ms** |
| 70 | `mine` | your own CSV/JSON: column profile, Pearson r with n, IQR outliers, group-by, trend slope, full report | action, path, column, other, key, value | **OK 0.6 ms** |
| 71 | `mentor` | SCAMPER, six hats, inversion, five whys, pre-mortem, first principles, second order, question banks | action, subject | **OK 0.2 ms** |
| 72 | `foresight` | least-squares extrapolation with an error band, three scenarios, verify checklist, and an explicit "I do not know" about live events | action, question, values, periods | **OK 0.2 ms** |
| 73 | `secure` | **defensive only**: password entropy and crack-time for your own password, phishing signals, this PC's posture, recovery plan | action, text | **OK 1.5 ms** |
| 74 | `facts` | the library: 75 dated + sourced facts across 8 domains, your own indexed files quoted by name, and a live Wikipedia lookup that cites its date — or an honest "I do not know" with a link | action, question, domain, topic, path | **OK 0.2 ms** |

| 75 | `video_studio` | 10 templates (reel, story, ad, hotel tour, teaser, slideshow…), 26 real transitions, 17 looks, any aspect (9:16 · 4:5 · 1:1 · 16:9 · 21:9), burned title/subtitle, music bed with sidechain ducking | action, clips, template, transition, look, music, title, seconds, fps | **OK 200 ms** |
| 76 | `audio_studio` | denoise (afftdn), de-ess, gate, compressor, 3-band EQ, reverb, broadcast loudness (-14/-16 LUFS), tempo without pitch shift, silence trim, chapter timecodes, waveform PNG, multi-track mix, music ducking | action, path, clips, gains, target_lufs, bass/mid/treble | **OK 165 ms** |
| 77 | `image_studio` | 16 looks (cinematic, teal-orange, noir, vintage, cyberpunk, duotone, tilt-shift, bloom…), finished cards at exact platform sizes (1080×1080, 1080×1920, 1280×720, passport 413×531), collages, whole-folder batch grading | action, path, images, look, template, title, subtitle, strength | **OK 8 ms** |
| 78 | `play` | **starts a real player process** — mpv → vlc → ffplay → mplayer → your OS default — names the file, measures the start in ms, queues the top hits, stops on command | action, query, kind, path, folder, queue | skip |
| 79 | `library` | read-only index of songs and videos across every fixed and removable drive; phrase + token + fuzzy search over 20,000 rows in under 120 ms | action, roots, query, kind, limit | **OK 52 ms** |
| 80 | `plan` | deterministic think → steps → run for multi-part requests ("scan my disk and play X"); stops at the first error, prints what it really did | action, request, confirm | **OK 2 ms** |
| 81 | `coach` | listen · mentor · analyst · decide · plan · check-in · journal · reflection — options with trade-offs, a recommendation, a confidence line, and real helpline numbers in a crisis | mode, text, options, action | **OK 1 ms** |

| 82 | `explain` | reads an error you typed, copied, or that is on screen (OCR) and names it: meaning, ordered causes, ordered steps, a confidence class — or a plain "I do not recognise this one" | text, where | **OK 4 ms** |

| 83 | `search_inside` | searches the **words inside** Word, Excel, PowerPoint, PDF, CSV and text files, and quotes the matching line with its file and line number. Incremental: unchanged files are never re-read | action, query, roots, ocr, limit | **OK 2 ms** |

| 84 | `pc_health` | **why is it slow**: two measured samples a second apart, then the actual cause with the number that proves it — RAM pressure, paging, a CPU hog, a full drive, disk saturation, startup bloat, heat — plus ordered fixes. Never kills or changes anything | action, text | **OK 409 ms** |

| 85 | `backup` | copies your own folders to another disk and **proves it**: SHA-256 of every file on the destination, a manifest per run, a new timestamped folder each time, and refusals for into-itself / drive-root / not-enough-room | action, source, target, include, verify, dry_run | **GUARD** |
| 86 | `autostart` | start with your account: one per-user entry, no admin, verified by reading it back, removable here or in Task Manager | action | **OK 0 ms** |

### Wave 11 — the vault, the speed, and one double-click

Four things the user asked for in one message, and what each one actually became.

**1-2. "Where does my work save? And progress too, like a vault."**
`arcdesk/vault.py`, one tool (`vault`), one folder:

```
%APPDATA%\ArcDesk\vault\            (movable: Settings → Vault, any drive)
    projects\belagavi-cafe-site\
        project.json       name, created, updated, counts
        notes.md           your notes, in order, readable in Notepad
        progress.jsonl     one line per answer/checkpoint, with the time
        files\             anything you added (COPIES — your originals stay put)
```

| Question | Answer |
|---|---|
| Does my progress save by itself? | Yes. Every answer the app produces is appended to the open project's `%APPDATA%\ArcDesk\vault\...\progress.jsonl` — measured at **0.45 ms** per save, so it can run on every reply. |
| Can I take it outside Jarvis? | `"export this project to my desktop"` — a new `ArcVault-<name>-<timestamp>` folder, size-verified file by file. Two exports never merge. |
| Can it overwrite my work? | Never. Adding a file copies it; a same-named file becomes `name-2.ext`; export refuses to write inside the vault. |
| What if the power dies mid-write? | The torn last line of `%APPDATA%\ArcDesk\vault\...\progress.jsonl` is skipped, the rest loads, and the next save repairs the newline instead of gluing two records together (that was a real bug, found by the test). |
| Is it a database? | No. Plain files. Copy the folder to a pen drive and it still works. |

**3-4. "Answers must be fast."** `tools/speedcheck.py` — measured on this machine:

| Path | p50 | Note |
|---|---|---|
| Lite brain (offline, typed command) | **0.28 ms** | p95 0.50 ms, 80 runs |
| Routing a request to the right tools | **1.01 ms** | was **75 ms** — see below |
| A real tool call (exact arithmetic) | 0.01 ms | |
| Vault checkpoint (every answer) | 0.45 ms | |

The 75 → 1 ms fix is the interesting one: `select.score()` was re-tokenising all tool
descriptions and re-scanning the whole synonym table **once per tool**, 87 times per
sentence. Token bags are now cached and the sentence is analysed once. Seventy-four times
faster, no behaviour change (routing tests unchanged).

**5. "One file, double-click, everything installed."** See `packaging/`:

| Step | Command | What it does |
|---|---|---|
| fetch | `packaging\fetch_runtime.py` | downloads ffmpeg + node **once, on the build machine**, checksum-verified where a checksum is published |
| build | `packaging\build_all.bat` | one command: runtimes → pre-flight → two exes → one installer |
| ship | `dist\ArcDeskSetup.exe` | per-user, no admin, no Python/ffmpeg/PATH setup. Last screen: *"Arc Desk is installed successfully."* |

Python is **not** shipped separately: PyInstaller already put an interpreter inside
`ArcDesk.exe`. Bundled ffmpeg/node are added to the app's own process PATH at startup —
nothing is written to the system PATH or the registry, so uninstall leaves Windows clean.

**7. "Compress the size."** Measured here, not estimated: the media payload is 195 MB of
`ffmpeg.exe` + DLLs and lzma2 (what Inno uses) brings it to **58 MB — 29%**. Honest limit:
the final `Setup.exe` number can only be printed by `packaging\build_all.bat` after Inno runs on
Windows; this is the measured input to it. And three compressions are refused on purpose:
one-file packing (unpacks to `%TEMP%` every launch), UPX (antivirus false positives), and
cutting Qt modules the app actually uses.

**Also fixed while doing this:** `find_files` — Lite emitted a tool name that does not
exist (the registry has `find_file`), so "find my report" silently never worked. There is
now a static guard in `tests/test_lite_intents.py` that reads every `_call("...")` in
`lite.py` and fails if any name is not in the registry — 79 names, 0 unknown.

### Wave 10 — "close" means close

The acceptance criterion was always *"HEY JARVIS opens it, BYE JARVIS closes it"*. Cross-
checking against the code found that the second half was only half true.

| Was | Now | Proof |
|---|---|---|
| `bye_action` defaulted to `hide` — "bye jarvis" hid the window and the app kept running | default is `exit` — the process really ends | `tests/test_voice_close.py` |
| "bye jarvis" with magic mode **off** only printed *"exit phrase heard, but magic mode is not active"* — nothing closed | it closes the app the same way it does after magic mode | same test, section 4 |
| Closing could leave nothing listening (no `sounddevice` / no engine), so "hey jarvis" could never reopen it — a dead end | the app proves the launcher is **alive for 1.5 s** before it quits; if it cannot stay, the app keeps itself open and says why | `_arm_launcher()` + `tests/test_app_lifecycle.py` case 2b |
| Settings offered 2 choices | 3: close+launcher, close+nothing, hide | `tests/test_voice_close.py` section 5 |

New tooling in this wave: `tools/voice_roundtrip.py` (drives the REAL app with the REAL
protocol and checks the process exit code), and `tools/crosscheck.py` — one command that
walks every designed feature and marks it **present / proven / failed / cannot prove here**.
Its current run: **15 present · 42 proven · 0 failed · 4 unprovable on this machine**
(saved to `CROSSCHECK.md`).

Also fixed while cross-checking: the whole `packaging/` folder had to be renamed from
`build/` — a folder called `build` is treated as disposable by build tools *and* by this
project's own workspace snapshots, which is exactly how the spec disappeared once.

### Wave 9 — the build, the reference, and the last two percent

Everything below was a **claim with nothing behind it** before this wave. Each row is now
checked by an executed command, not by intent.

| Was | Now | How it is checked |
|---|---|---|
| README and `INSTALL.md` described `packaging\build.bat` and a PyInstaller spec that **did not exist** | `packaging/arcdesk.spec`, `packaging/build.bat`, `packaging/arcdesk.iss`, `packaging/make_installer.bat` all exist and parse | `tools/packaging.py` → `checked 35 · needs windows 3 · failed 0` |
| The "two exes" claim | one spec, two `Analysis`+`EXE` targets: `ArcDesk.exe` (window) and `ArcDeskVoice.exe` (the ears) | `tests/test_packaging.py` |
| A specified module list would rot | `collect_submodules("arcdesk")` — new modules are in the build automatically; a hand-written list now **fails** the check | `packaging.py` rule + test |
| The generated pages were shipped in neither the spec nor the app | the spec bundles `arcdesk/*.html` (they live in the package, not the repo root — that mistake was found and fixed here) | spec assertion |
| No icon | `shots/arc_icon.ico` + `.png` drawn by `tools/make_icon.py` (7 sizes, 16–256 px, original artwork) | file + ICO header test |
| 88 tools described only in prose | `TOOLS.md` + `arcdesk/TOOLS_PAGE.html`, generated from the registry, searchable, offline | `tools/gen_tools_doc.py --check` is a *step* of `check.bat` |
| Nobody ever ran the real entry point | `tools/smoke_firstrun.py` boots `run.py --shadow`, checks settings were written, sends a stop signal, expects exit 0 and the words "closed cleanly" | `tests/test_firstrun.py` |
| `uninstall.bat` did `taskkill /IM pythonw.exe /F` — which kills **every** Python GUI app on the machine | it now matches its own executable names and its own command line only | `packaging.py` rule + test |
| Ctrl+C left a `KeyboardInterrupt` traceback and could keep the instance lock | a signal handler sets a flag, a 200 ms timer quits Qt; measured clean exit 0 at 4 s, 5 s, 6 s and 7 s | `tests/test_firstrun.py` |
| The first-run wizard's `dlg.exec()` ignored the stop signal (nested event loop) | the wizard is shown and the main loop is pumped, so a stop falls straight out | test + comment at the code |

The tool count is unchanged at **86** — this wave added no capability, it made the existing
ones *provable*. That is the honest summary of a wave like this.

### Wave 8 — the three things your setup was missing

**Backup that proves itself.** The first rule in this project is *your files are never
damaged*, and until now ARC could read files but not protect them.

| Question | Answer |
|---|---|
| Does it verify? | Every file is hashed **while it is copied** (one pass, the source is never re-read), then the copy on the destination is hashed again and compared. The reply says `verified: all N files re-hashed and matched (SHA-256)` — or names the files that did **not** match and tells you not to trust that copy. |
| Can it overwrite anything? | No. Each run creates `ArcBackup-<timestamp>`; a second run on the same minute makes `-2`. A test runs it twice and asserts both folders exist afterwards. |
| Does it touch the source? | Opened read-only, `copystat` is applied to the **destination**. A test snapshots every source file's mtime+size before and after and compares. |
| When does it refuse? | Target inside the source (would grow forever), source inside target, same folder, a whole drive root, a missing path, and — before writing a byte — "not enough room: 12 GB to copy, 4 GB free". |
| Can I check an old backup? | `verify backup D:\ArcBackup-…` re-hashes it against its own manifest. A tampered file is reported by name. |

**Start with Windows, on purpose.** One `HKCU\…\Run` value (`ArcDesk`) — per-user, no
admin, no service, no scheduled task with SYSTEM rights. It is read back after writing,
so "enabled" is what the registry says, not what the code intended. If the install moves,
`status` reports it as **stale** instead of claiming it works. It appears in Task Manager
→ Startup apps like any other program and disabling it here deletes the value. **Off
unless you ask** — the wizard's checkbox starts unticked.

**First run, five decisions with their costs written on them.** Voice (the OS voice, no
extra download), wake word (a 60–150 MB daemon and a live microphone), autostart (runs at
every login until you say no), document search (reads Documents/Desktop/Downloads once,
read-only). Everything is applied by `arcdesk/firstrun.py`, which is also what the voice
command "start with windows" goes through — one implementation, two ways in.

### Wave 7 — "yen slow da?"

`system_report` shows numbers; this says what they mean and what to do. The difference
between the two is the whole feature.

| Question | Answer |
|---|---|
| How does it decide? | **Two samples, one second apart**, so CPU per process is a real delta rather than a lucky instant. Every finding quotes the measurement that fired it: *"7.7 of 8.0 GB used (96%) — biggest single app: chrome.exe at 3.0 GB"*. |
| What does it check? | 11 rules: RAM pressure, pagefile/swap thrash, one CPU-hungry process, whole-CPU load, nearly-full drive, disk throughput saturation, startup bloat (read read-only from the registry), process count, low battery under load, thermal throttling, long uptime. |
| Severity? | **high** = this is really your slowdown; **medium** = worth tidying; **note** = information, explicitly not a fault (e.g. 300 processes is normal on a modern machine). |
| Heat? | Only if your machine exposes a sensor. If it does not, the reply says *"this machine exposes no sensor to software, so I did not measure heat at all (not 'it is cool' — 'I cannot see it')"*. |
| Does it close apps? | **Never.** It names the app holding 3 GB and says: *"ARC will not kill it for you: say 'close chrome' and it asks first."* Nothing is killed, no setting, service or registry value is changed. |
| Faster version? | `"pc_health quick"` — one line: `CPU 1% · RAM 45% · disk 80% free · fine`. |
| Startup? | `"startup items"` lists every Run-key entry with its scope, and warns which ones never to disable (Security, Audio, Touchpad, Graphics). |

### Wave 6 — the words inside your files

`search.py` answers *"where is budget.xlsx?"*. This answers *"which of my files mentions
the Hampi advance?"* — which is what people actually need, and what a filename index
cannot do.

| Question | Answer |
|---|---|
| What is searched? | Word, Excel, PowerPoint, PDF, CSV/TSV/JSON and plain text. It reuses `reading.py` — the same extractor the read tool uses — so there is one place to fix, not two. |
| What comes back? | The file, its type and size, **the line number**, and the exact sentence around the match, then the full path. Every hit is checkable at a glance instead of asking you to trust a score. |
| Is it fast? | A 4-document folder indexed in **14 ms**; the second run re-reads **0** files in **0.3 ms** because every file is remembered by size + mtime. Files with no text layer (scans, binaries) are remembered too, so a 50 MB scanned PDF is not re-read on every pass. |
| Does it touch my files? | Read-only `os.stat` and reads. It writes exactly one JSON index inside ARC's own data folder, and `forget` deletes only that. A test snapshots every file's mtime and size before and after to prove it. |
| Scanned PDFs? | They have no text layer, so they are counted and named in the reply — not silently treated as empty. `index my documents with ocr` adds images/scans (about a second each) and says so first. |
| What if nothing matches? | It says how many files it searched, how many had no text layer, and offers the OCR pass — it never returns a "best guess" file. |
| Partial matches? | If no file has every word, the reply says so in the first line ("no file has all the words… these are partial matches") instead of quietly ranking a weak hit first. |

### Wave 5b — "idhu enna error da"

The most common thing anyone wants from a computer at 11 p.m. is not a poem. It is
*"what is this thing telling me?"* `arcdesk/screenhelp.py` is **not** a language model: it is
24 hand-written error families, each matched against the literal text on screen.

| Question | Answer |
|---|---|
| Which errors? | Windows start-up and BSOD codes (`0xc000007b`, `0x80070005`, stop codes), SmartScreen, services, Windows Update; Python tracebacks / `ModuleNotFoundError` / syntax / permissions; git; DNS, connection-refused, 404, TLS, offline; ffmpeg, locked files, corrupt documents, no audio device, unreadable USB disks. |
| Where does the text come from? | You type it, you copy it (clipboard), or ARC **screenshots and OCRs the screen** — `vision.py` already had the eyes; this gives them a use. |
| How sure is it? | Every family is labelled **certain** (a documented code, fixed meaning) or **likely** (wording varies between versions). The reply says which, and always adds: *your specific machine and files: unknown until you try step 1*. |
| What if it does not know? | It quotes the exact line it read back to you, says "I do not recognise this error — so I will not guess at a cause", and offers a search built from your own words. **A wrong fix at midnight is worse than no fix.** |
| Does it ever refuse a diagnosis? | Yes, three ways: text saying "0 errors" is believed rather than second-guessed; a photo/wallpaper is not diagnosed; and `unexpected`/unknown messages get no steps at all. |
| Can it fix things for me? | Only where that is honest. It never asks for admin, never touches Windows components, never writes over a file — and each family says so explicitly when that is the limit (`ARC: nothing here — …`). |

### Wave 5 — playing, scanning, thinking, and a mentor who does not flatter

| Question | Answer |
|---|---|
| Does "play X" actually play? | Yes — a real process. Order is mpv → vlc → ffplay → mplayer → the OS handler. A player that exits inside 350 ms is treated as a **failure** and its error is shown, so a broken codec looks like a broken codec instead of silence. Start time is measured and printed (`started in 6 ms`). |
| Where does it look for songs? | `arcdesk/library.py` indexes audio and video from your home music/video folders, every fixed and removable drive, and `/media`, `/run/media`, `/mnt`, `/Volumes`. Nothing is copied, renamed or written into your folders — the index is one JSON file in ARC's own data folder. |
| And an external disk? | "scan my E drive" / "scan the external hard disk" scans it read-only. If the disk is unplugged, ARC says so and **leaves the previous index alone** instead of quietly replacing it with the default folders. |
| What about a name I half-remember? | Phrase, then token, then fuzzy (difflib) scoring. `"ilaiya nila"` still finds *Ilaya Nila*. Track numbers, `(Official Video)` and `[320kbps]` are stripped from what ARC shows — but the file path is always the real one, and a file with embedded tags keeps its tags. |
| "Instant answers, no buffering"? | The media index, playback, the planner and the coach are all **local and deterministic** — no model round-trip, no network. Measured here: 20,000 indexed rows searched in **110 ms**, playback start **0–9 ms**, a plan in **2 ms**. Long renders still exist, and they say `measured` or `rough` rather than inventing a number. |
| Does it think before acting? | `arcdesk/planner.py` turns *"scan my external disk and play kabira"* into two named steps, prints them with `✓`, and stops at the first `ERROR:` rather than flailing. Six steps maximum — a request that needs more is answered with what it will not guess. |
| Mentor / analyst / wellwisher? | `arcdesk/coach.py`. **listen** reflects your words and asks at most one question; **mentor** gives a frame and one action for today; **analyst** reads only numbers you supply and tags anything else as a guess; **decide** asks what is reversible, what you are optimising, and what doing nothing costs; **plan** writes seven days; **journal** and **reflection** count only entries you really wrote. Every answer carries `(framework, not a prophecy)` or a confidence line. |
| Feelings? | It notices tone from your own sentence ("i feel low", "romba tired") and answers in kind — Tanglish in, Tanglish out. It never diagnoses, never says "cheer up", and never turns a bad day into a productivity lecture. |
| Crisis? | Real numbers, immediately: **Tele-MANAS 14416**, KIRAN 1800-599-0019, **112**, 988, 116 123 — plus a plain statement that ARC is software, not a clinician. |

### The studio — video, audio and images, done properly

`edit_file` does one operation to one file. The three studio tools *compose*: a reel
out of six clips, a podcast mix with the music ducking under the voice, a story card
at the exact size Instagram wants. Everything is ffmpeg + Pillow on your own machine.

| Question | Answer |
|---|---|
| Transitions? | 26 real `xfade` transitions — fade, dissolve, wipe (4 directions), slide (4), circle, radial, smooth, diagonal, pixelize, hblur, zoomin, squeeze, cover, reveal. Plus a hard cut. |
| Looks? | 17 video grades and 16 photo grades, all built from real filters (`colorbalance`, `curves`, `eq`, `unsharp`, `noise`, `vignette`, `gblur`), and a `strength` control that blends the original back in. |
| Titles? | Burned with `drawtext` via a text file, so colons, quotes and ₹ never break the filter graph. |
| Music? | `sidechaincompress` — the bed drops under the voice automatically. It will **not** synthesise a track: missing file = refusal with the path it wanted. |
| Loudness? | `loudnorm` to -14 LUFS (social) or -16 (podcast), measured by ffmpeg, not guessed. |
| Aspect? | 9:16, 4:5, 1:1, 16:9, 4:3, 21:9 — every clip is scaled and padded, so mixed footage cuts without the bars jumping. |
| Captions? | It burns an `.srt` you supply. It will not invent words — that needs a local ASR model. |
| Cost? | Zero. ffmpeg and Pillow are already free; nothing is uploaded, nothing is per-minute. |

**Original files are never touched.** Compositions land in `<data>/studio/`, single-file
looks write a sibling, and two renders in the same second get `_2`, `_3` suffixes so
one can never overwrite the other — `tests/test_media.py` measures the output of each
path (1080×1920 for a story, 2.93 s for a 2 s + 1.5 s pair with a 0.6 s cross-fade).

### The library — what "knows everything" honestly means

"Everything" is not a memory that can invent. Tool 74 has exactly four sources, and
it names which one it used:

| Source | Covers | Never does |
|---|---|---|
| **Shelf** — `arcdesk/world.py`, 75 entries, each with a source and a year | stable facts: India (28 states + 8 UTs, 7,516 km coastline, GST slabs), world, science (8,848.86 m, 8 bits), tech, money, health (CPR 30:2), food, myths | state a drifting number (population, CO₂, repo rate) without its year |
| **Your files** — `facts{action:ingest}` indexes any folder | your notes, SOPs, price lists, contracts — quoted with the filename | paraphrase your file into a claim it does not make |
| **A live lookup** — `facts{action:fetch}` goes to Wikipedia, caches for a week | anything with an article, with the URL and the date it was read | answer from memory when the network is down — it says so |
| **The machine itself** — `system_report`, `time`, `briefing`, `search` | clock, CPU, RAM, disk, your files | print a number it did not measure |

Anything outside those four — tonight's news, a price, who holds office right now —
comes back as *"I do not know that one, and I will not improvise it"* with a real
search link. A library that invents an answer is worse than one that admits the edge.

### Two things that are deliberately *not* tools

**Hacking, password breaking, covert access.** `secure` refuses them in code, with the
reason (unauthorised access under s.66 IT Act and similar laws; and a desktop app that
can quietly open a door is a backdoor, so antivirus would be right to flag the whole
program). What remains is what actually protects you: entropy you can measure,
phishing you can spot, your own machine's posture, and a recovery plan.

**Predictions sold as facts.** `foresight` will extrapolate your own numbers and show
the error band, or lay out three scenarios with their assumptions — but it will not
claim to know what will happen, and it says "I do not have a live news feed" instead of
narrating world events from memory.

### The day layer — three tools that make ARC a companion, not a remote control

| Ask | What happens |
|---|---|
| *"remind me in 20 minutes to stretch"* | a real reminder in a JSON file inside the app's data folder; when it comes, ARC speaks it once and marks it said |
| *"start a focus session for 25 minutes"* | timer starts; ARC stays quiet; when it ends it says *"Your 25-minute focus block is done — take a break"* |
| *"how long is left in focus"* | real remaining time, not an estimate |
| *"good morning"* | clock + date, today's calendar, due reminders, focus minutes, CPU/RAM/disk — every number measured |
| *"which open source package can read a pdf"* | search of the 86-package catalogue, ranked, with licences |
| *"scan my github stack"* | which of those are actually on this PC, and the exact free install command for the rest |

None of these need a model, a key, or the internet. `window.py` checks reminders and
focus blocks on a 15-second timer, so a reminder is never late by more than a quarter
of a minute and never announced twice (each reminder carries a `said` flag).

### Tool routing — 73 in the catalogue, a handful per request

`arcdesk/ai/select.py` scores every tool against the sentence and sends the best
`k` (default 8) plus `list_tools`, so an unrouted tool is never unreachable.

| Measurement | Full catalogue | Routed |
|---|---|---|
| Tools in the request | 73 | 4–9 |
| Prompt tokens for the schema | **3 549** | **178–650** |
| Works in a 2 048-token context | ✗ (`you requested 4210 tokens`) | ✓ |
| 0.5B model picks the right tool | sometimes | yes, 24/24 phrases in `test_select.py` |

Measured on a real llama.cpp server with Qwen2.5-0.5B-Instruct, 2 CPU threads:

| Round | Prompt | Completion | Time |
|---|---|---|---|
| 1 — "what time is it, how much ram am i using" | 642 tok | 15 tok | 0.6–8.8 s (cold page-in) |
| 2 — after the tool result | 695 tok | 37 tok | 2.1–2.7 s |

The same phrase through the Lite brain: **0.7 ms**. That gap is the honest reason
ARC answers routine commands without waking a model at all.

Plus **every tool any MCP server exposes**, reachable as `mcp__<server>__<tool>` —
unknown at build time, discovered at runtime.

---

## Wave 26 — one file that answers "what is missing on my laptop?"

Asked for directly: *"arcdesk laptop la run pana missing ah irukura things, then athula
again add pana download pana vendiya things… oru file la kodu… sandbox la run pana pothu
yethu irunthuchu, appadiyae intha ArcDesk.exe layum irukanum."*

- **new `tools/parity.py` → `WHATS_INCLUDED.md`** — three lists that are never typed by
  hand: **(A)** what is already inside the `.exe` (every `arcdesk` module, the two helper
  scripts carried as data, and each library with a live *"can this machine import it?"*
  rather than a filename check), **(B)** what is downloaded after install — seven rows,
  each with its real size, the exact folder it lands in, the button that fetches it and
  the feature it unlocks, **(C)** what deliberately never ships (torch/IndicF5, XTTS,
  llama.cpp + GGUF) with the reason and the private-environment route used instead. Plus
  a table of what the app writes to `%APPDATA%\\ArcDesk`, and the five first-run steps.
- **the parity check is a measurement, not a promise**: the document states whether the
  build installs each hard dependency, whether the voice libraries are attempted
  separately, and whether the spec collects the wake engine at all — read out of
  `.github/workflows/build-windows.yml` and `packaging/arcdesk.spec` at generation time.
- **one honest subtlety found while writing it**: `sounddevice` is *installed* in the
  sandbox but cannot *import* there (no PortAudio on Linux), while on Windows the wheel
  carries its own DLL. The generator reports "yes, but import fails here (OSError)"
  instead of a bare "yes", because that distinction is the whole reason a build can look
  complete and still be silent.
- **new `tests/test_parity.py`** (6 sections): the document is byte-identical to a fresh
  generation (`--check`), the module count is the real count and comes from
  `collect_submodules`, both helper scripts are in the spec's datas, the wake engine is
  collected, every non-shipped item has a size and a destination, and the sandbox column
  distinguishes installed from importable.

## Wave 25 — a brain in the box, the name JARVIS, and the step you can watch

Four requests in one message: *"romba hang… task work aagutha nu theriya matiku…
task process ena nu therinja nalla irukum… esc kodutha close aaga matiku… no local model
detected nu varuthu, brain ah add pana solluthu, athayum oru bundle ah koduthudu… athu
pesum pothu 'I am ARC' nu soluthu, 'I am JARVIS' nu sonna semaya irukum."*

- **new `arcdesk/brain.py` + `widgets/brain_dialog.py`** — *the brain is now a bundle*.
  A small local model (**Qwen2.5 1.5B**, 1066 MB, tool-capable; **0.5B**, 469 MB,
  chat-only and labelled as such) downloaded from huggingface, run by
  `llama-cpp-python[server]` **bound to 127.0.0.1:8010**, started by the app, and written
  into the config so the next question uses it. Sizes are stated before the download,
  Stop works, the verdict is honest, and **Lite keeps answering throughout** — a brain
  that is not ready must never be a dead app. On the installed `.exe` it uses the same
  private environment as the voice engine (a compiled app cannot import a package that
  arrives later), and with no Python at all it says so in one sentence instead of hanging.
  Reachable from the setup card ("no local model detected" now has a button on it) and
  from Settings → Local AI.
- **new `arcdesk/identity.py`** — the spoken name is **JARVIS**, one setting
  (`ai.name`), used by the persona prompt, the Lite self-introduction, the first-run voice
  test and the dashboard. The prompt says it as identity: *"Your name is JARVIS… never
  'I am ARC'. Arc Desk is the window."* Editable in Settings → Local AI ("It calls itself:").
- **the step on screen**: `Agent` now emits `step_started` / `step_finished` for the model
  turn and for every tool, and the console keeps a **process strip** — `▸ tool: open_app`
  becomes `✔ tool: open_app 0.3 s` in place, in order, for the current request. With the
  seconds counter above it, "is it doing anything?" is answered twice, in two ways.
- **Esc, belt and braces**: `handle_escape()` was already one ladder, but it relied on a
  keyPressEvent and an event filter. It is now also an **`ApplicationShortcut` QShortcut**,
  which Qt delivers even when a text field owns the focus — the exact case that made Esc
  do nothing. The ladder: dialog → speech → running task → palette/console/holo →
  hide the window → (already hidden) quit. `Ctrl+Alt+H` hides without touching the task.
- **the dashboard stopped being half empty**: a new status card states, in three lines,
  `BRAIN · JARVIS · Lite (offline, instant)`, `EARS · not ready (…)`, `VOICE · …`, using
  the same wording as Settings (one function, `reply_voice_line(cfg)`), refreshed every
  10 s so the TCP probe costs nothing.
- **`tests/test_brain.py`** (7 sections): the name in the persona/Lite/intro, both models
  and their sizes, packages-then-weights-then-server, the URL it writes into the config,
  the no-Python case, the dialog's three verdicts, and the two places it is reachable
  from. `tests/test_activity.py` gained the process strip and the application-wide Esc
  shortcut.

## Wave 24 — white letters on a white box, and a model that was there all along

Two things from one screenshot, and they were unrelated:

- **white on white.** The engine and ears dialogs were built with Qt's default palette.
  The window came out white, the log came out white, and because `appendPlainText` gives a
  `QPlainTextEdit` the focus, every line was drawn **as a selection highlight**. New
  **`arcdesk/widgets/style.py`**: `dialog_style(theme)` is one stylesheet (window, labels,
  log, combo boxes, lists, buttons, progress bar) built from the arc theme, and
  `read_only_log()` makes a log read-only, `NoFocus`, and `NoTextInteraction` — it cannot
  take the keyboard, so it cannot paint itself. Applied to the ears dialog, the engine
  dialog and the voice library.
- **"speech model not downloaded" one line after "already present: …\ArcDesk\vosk-model-small-en-us-0.15".**
  Two folders for one feature: `arc_daemon.py --download-model` unpacks to
  `<data>/vosk-model-small-en-us-0.15`, and `voice_ready.model_dir()` only looked in
  `<data>/models/vosk` and `<data>/vosk-model`. So on that machine **"hey jarvis" could
  never work, however many times the model was downloaded** — the app was telling the
  truth twice and contradicting itself. One list now (`voice_ready.model_candidates()`),
  used by the ears dialog, the setup card and the doctor, and a folder only counts when it
  really is a Vosk model (`am/` or `conf/` inside it), not when it merely has the name.
- **new `tests/test_theme.py`** (6 sections): all three dialogs carry the theme's colours
  and no plain white, logs are read-only + unfocusable + unselectable, the downloader's
  folder is found, an empty or merely-containing folder is refused, the older layouts
  still work, the candidate list is de-duplicated, and the honest sentence changes when
  the model appears. `tests/test_ears.py` gained a section asserting the checker and the
  downloader name the same folder.

## Wave 23 — "is it doing anything?", and an Esc that always works

Reported: *"romba hang and slow ah iruku even task assign pana work aagutha nu theriya
matiku, ena work nadakuthu nu therinja nalla irukum. esc kodutha close aaga matiku."*
Three separate problems hiding behind the word "hang".

- **new `arcdesk/activity.py`** — one thread-safe record of what is happening: the live
  step (`tool: open_app`), a **seconds counter that keeps moving** (a clock that advances
  is the difference between "working" and "wedged"), a timeline of finished steps, and a
  **cancel flag the agent checks between steps**. Pure Python, no Qt, so it is tested
  without a screen.
- **the console shows it**: a dot, a live line (`tool: open_app · 1.4 s`) refreshed every
  150 ms, and a **STOP** button next to it. When a request takes ≥ 1.5 s, the finished
  steps are appended to the transcript (`tool: open_app → tool: system_report · total
  4.2 s`) — so "what did it do?" never needs a log file.
- **Stop really stops**: `Agent._execute` refuses to start the next tool once the flag is
  set (`"stopped before running (you pressed Stop)"`), a slow tool gets its own time
  attached, and a tool that raises no longer kills the turn.
- **Esc, from anywhere.** `handle_escape()` is one decision — stop speech → stop the task
  → close the palette → close the console → hide the window — and it is reached through
  an **application-wide event filter**, because `keyPressEvent` never fires when the chat
  field, the transcript or the palette holds the focus. That was the exact bug: Esc did
  nothing because a text widget had the keyboard. When a dialog is on top, the filter
  steps back and lets the dialog close itself (so the setup card still saves its answer).
- **the window stops animating when it is hidden.** Stealth is the resting state, so the
  app used to repaint a 30 fps reactor a window nobody could see, all day, on a laptop.
  `showEvent`/`hideEvent` now pause and resume the shared ticker.
- **the frame rate protects itself.** `FrameTicker` measures how long each frame's
  handlers really took (`ms/frame`, smoothed) and drops the rate in steps when the machine
  cannot afford it, climbing back when it can. And `_apply_guards()` — which runs every
  10 s — now calls `set_base_fps()` instead of `set_fps()`, because it used to **undo that
  slowdown every ten seconds**; on a weak laptop the app was permanently behind, which is
  exactly what "romba slow" feels like. The footer now prints the real cost:
  `ARC CORE 180 MB · 30 FPS · 4.1 ms/frame`.
- **new `tests/test_activity.py`** (8 sections): the record and its clock, the agent
  refusing the next tool after Stop, the console's live line and STOP, Esc delivered to a
  focused chat field actually cancelling the task, Esc closing the console and hiding an
  idle window, the ticker pausing while hidden, the frame-rate guard slowing down and
  recovering (and not being reset by the 10-second guard), and the trail being readable
  afterwards.

## Wave 22 — why the first start looked broken, and why "hey jarvis" was silent

Reported, with a screenshot: *"this is what comes up. Nothing else of ArcDesk opens. Close
it and double-click again — same. Voice command gets no response. And by default floating
icons appear on the desktop."* Three real bugs, none of them cosmetic:

- **the setup card trapped the person.** Five cards plus a footer in a plain vertical
  layout — taller than a laptop screen, so **"Done" was laid out below the visible area**
  and could never be clicked. The only way out was the ✕, which saved nothing, so
  `first_run` stayed true and the card came back on every launch. Fixed: the cards live in
  a **QScrollArea**, the footer with *Start ARC / Just use Lite* is pinned outside it, the
  dialog sizes itself to 90% of the screen, and **Start ARC is the default button** (Enter
  works). Every exit — ✕, Esc, Start, Skip — now saves an answer.
- **nothing opened afterwards.** Stealth mode hides the window at boot (that is the
  promised resting state), so once the card was answered the app was invisible. New
  `firstrun.reveal_window()`: answering the card means somebody is looking at the screen,
  so the window appears **once**; later launches stay silent.
- **floating icons on the desktop by default.** `charms.enabled` was `true` in the
  defaults. Now **off**, with a one-time `config._migrate()` that switches off the old
  default for existing settings files **only where nobody ever chose it**
  (`user_choice` is set the moment they toggle it in Settings) and keeps their decorations.
  Side effect found and fixed: with charms off, nothing called `save()` at boot, so a fresh
  install had no `settings.json` at all — the app now writes it on first start.
- **"hey jarvis" had no ears.** The card had already admitted, in small grey text, *"no
  wake-word engine is (openwakeword or vosk)"* — and offered nothing to do about it. New
  **`arcdesk/ears.py` + `widgets/ears_dialog.py`**: four separate requirements (microphone
  library · wake engine · 40 MB speech model · 30 MB speaker model) each ticked or crossed,
  one button that installs/downloads what can be done from inside the app with live output,
  a Stop that really stops, and then a **re-check** — never "ready" because a download
  finished. Reachable from the setup card (only when the machine cannot listen) and from
  Settings → Voice.
- **the build now proves the ears are in the .exe.** The CI step installed
  `vosk sounddevice sherpa-onnx` in one command, so one bad wheel silently sank all three;
  it is now one package at a time, with a line that prints which of
  `sounddevice / vosk / openwakeword / sherpa_onnx` are actually bundled, and
  `packaging/arcdesk.spec` collects them and says so in the build log.
- **new `tests/test_startup.py`** (6 sections, real Qt offscreen): the footer is reachable
  in a 560-pixel-tall window, all four exits save an answer, the defaults really are
  icon-mode + mic off, `reveal_window()` covers all three cases, the charms default and
  the migration (including "a real choice is never overruled"), and a real `MainWindow`
  whose overlay starts hidden. **new `tests/test_ears.py`** (7 sections): the four
  requirements, the exact state the user reported, the fix that re-measures, cancel that
  stays cancelled, a compiled build that cannot add packages admitting it, and the dialog's
  three verdicts.

## Wave 21 — the neural engine, installed from inside the app

The user's sentence: *"Clone panna neural engine thevai. add this also."* A cloned voice
is not a preference, it is a model — and the app used to answer that with "run
install_clone.bat". Now it answers with a button.

- **new `arcdesk/engines.py`** — one module owns the whole "get the model" job:
  `status()` (what is installed, how big, why not), `method()` (how *this* build can
  install anything), `install()` (pip, then the weights, streaming every line),
  `sidecar_speak()` (one sentence, one wav). Four rules are encoded, not documented:
  nothing is ready until the **weights** are on disk, a failure keeps the real error
  line, a **cancelled** install is never reported as installed, and every size is stated
  before the download starts.
- **new `widgets/engine_dialog.py`** — Settings → Voice → **"Get the reply-voice
  engine…"**, and the same dialog from the voice library. One entry per engine
  (IndicF5 · Tamil/Hindi · 1.5 GB · XTTS-v2 · English · 1.9 GB), a button that carries the
  size, live output, a **Stop** that really stops, and a verdict that is either "ready" or
  the real reason — never a spinner that ends in nothing.
- **new `arcdesk/uiwork.py` — one way to wait, and it is never the drawing thread.**
  `run(work, done=…)` starts a daemon thread and delivers the answer to the UI thread
  through a `Signal` (the only cross-thread call Qt guarantees); `busy_cursor()` puts the
  waiting cursor back even when the work raises; `clear_stuck_cursors()` sweeps up any
  override that anything left behind; `StallWatch` is a 100 ms heartbeat that, when it is
  late, reports **which line froze the window** (read from the live frame of the main
  thread, sampled by a 50 ms profiler thread — a heartbeat alone can only say *that* it
  froze, not *where*).
- **new `arcdesk/blockguard.py` — the rule, enforced.** It wraps `subprocess.run/Popen`,
  `urllib.request.urlopen`, `socket.create_connection` and `time.sleep`, and when one of
  them is called from the drawing thread it writes
  `UI · widgets/engine_dialog.py:235 called subprocess.run on the drawing thread` and names
  three frames of the caller. The shipped app runs it in **warn** mode
  (`ARCDESK_UI_GUARD=1`); the test suite runs it in **strict** mode, where it raises — so a
  regression fails the build instead of being reported by a person with a screenshot.
- **new `tools/engine_get.py` — the same answers in a terminal.** `status`, `gate`,
  `install`, `token`: the .bat calls this instead of `python -c "from transformers …"`, so a
  gated model is refused **before** 200 MB of torch, the reason is one sentence instead of a
  traceback, and the exit code (0 done · 1 failed · 2 needs a token) is what the script
  branches on. It also fixed a real bug in the app: `engines.gate()` used to ask
  `api/models/<repo>` (which answers **200** even for gated repos) and now asks for a real
  file under `resolve/main/` (which answers **401**) — the same measurement the
  screenshot shows.
- **the installed `.exe` can do it too, honestly** — a frozen PyInstaller app cannot
  import a package installed later, and torch inside the installer would add ~2 GB. So
  the app borrows a Python already on the computer, builds a **private environment** in
  the user's data folder (`ArcDesk/engine_env`), installs the engine there, and speaks by
  handing one sentence to **new `tools/clone_speak.py`** with that interpreter (shipped
  inside the frozen app by the spec). Still one button; nothing global, nothing on PATH.
  With no Python on the machine the dialog says exactly that and points at python.org —
  it does not pretend.
- **new `tests/test_engines.py`** (10 sections, both child-process steps faked): sizes and
  languages before download, packages-then-weights ordering, a weights failure that must
  not read as success, Stop that must not read as success, the frozen route (no Python /
  Python found), the private-folder install, the sentence actually reaching
  `clone_speak.py`, `route("ta")` switching over only once the folder is ready, and the
  dialog's three verdicts.

## Wave 20 — the reply voice, in the app

The user's sentence: *"jarvis ku nan than command kodupen, so enoda voice ku athu respond
pananum."* Two voices, two questions — and until now only one of them had a button.

- **new `arcdesk/voicelib.py` + `widgets/voicelib_dialog.py`** — Settings → Voice →
  **"Voices…"** with two lists, because there are two questions:
  *who may command ARC* (any number of people, enrolled from a recording via
  `voiceid`, and `verify()` accepts the best match) and *which voice it answers in* (any
  clip you have — yours, or someone else's, each kept as its own graded file with its
  transcript and language). The chosen reply clip is mirrored to `reference.wav`, so the
  daemon and the CLI keep working off one source of truth.
- **new `tests/test_voicelib.py`** (8 sections, fake speaker engine + fake clone engine):
  adding two reply voices, switching between them, removing the active one without
  dangling the reference, enrolling two command voices, a different voice being refused,
  the dialog's two lists, and that the app never calls the system voice by your chosen
  name.
- **the app now states its reply voice in one line**: *"Reply voice: your own recording,
  spoken by indicf5"* or *"…the system voice — no clone engine installed (run
  install_clone.bat)"*. The question "why is the reply in a different voice?" can no longer
  be answered by guessing.
- **`ai.voice_clone` is a switch you can reach**, not a key in a JSON file.
- **cinematic cues, generated not downloaded**: seven short WAVs (`wake`, `magic_begin`,
  `magic_end`, `task_start`, `task_done`, `task_failed`, `click`) written by `arcdesk/sfx.py`
  in **0.15 s** into `%APPDATA%\ArcDesk\sfx\`, ~90 KB total — no audio library, no licence.
  Playback is on a daemon thread with a per-cue `min_gap`, so four tools finishing in one
  second chime once instead of sounding like a pinball machine, and a missing sound card
  cannot raise into the app.
- **a companion voice**: `arcdesk/companion_voice.py` — "Hi commander." on the wake word,
  "Thank you, commander." on the way out, and a task-related acknowledgement
  ("Opening Notepad, commander.", "Checking the machine, commander.") instead of a generic
  "OK". The honourific is a setting (`commander` by default, blank to drop it), and the
  acknowledgement is only spoken if the task is still running after **1.2 s** — a 4 ms Lite
  answer gets no chatter over it.
- **opened by hand is not opened in silence**: both doors into magic mode (the wake word
  and the magic button) run one guarded opener, so there is a beat and a "Hi commander"
  either way, and never twice if the two land in the same second. Before this, launching
  without the wake word had no cue and no greeting at all.
- **the goodbye is spoken before the close**, not cut off by it: `QTimer.singleShot(900 +
  55 × characters)` ms, so the sentence finishes and then the app hides or quits.
- **Settings → Sound** holds the switches, a volume slider with a "Hear one" button, the
  honourific field and a "Preview the lines" button — nothing about the sound is a
  config-file secret.
- **new `tests/test_cinematic.py`** (8 sections): the seven cues render small and fast, the
  whole set is mono 16-bit at 22 kHz, a play never blocks or raises, `min_gap` and the
  volume-keyed cache behave, every line is the exact requested sentence, the honourific
  works, the order is line-then-close, and the Settings switches exist and are saved.
- **no stray command prompt, ever** (`arcdesk/quiet.py`): ArcDesk is a windowless
  program, so on Windows every console child used to get a brand-new black window — one
  per spoken sentence (PowerShell SAPI), per screen read, per ffmpeg/tesseract pass, per
  wake-daemon restart. `-WindowStyle Hidden` is not a fix (PowerShell still shows the
  console first); `CREATE_NO_WINDOW` on the spawn is. **95 spawn sites in 24 modules** now
  go through one wrapper, and `tests/test_quiet.py` scans the source so a new
  `subprocess.run(` fails the suite instead of appearing on someone's screen.
  POSIX is unchanged: flags dropped, `start_new_session`/`DETACHED_PROCESS` translated.
- **`ArcDesk.pyw`** — the double-click launcher with no console behind it (`pythonw.exe`
  runs `.pyw`). It points a missing `stdout`/`stderr` at
  `%APPDATA%\ArcDesk\logs\arcdesk.log` first, because under `pythonw.exe` the first
  `print()` in `run.py` would otherwise raise `AttributeError` and the app would die
  before drawing anything. A windowless crash leaves a traceback there.
- **`tests/test_quiet.py`** (7 sections): the flag translation (measured on the Windows
  branch too), a real child still answering, `check=True` still raising, `shell=True`
  working, zero direct `subprocess` calls left in runtime code, the daemon spawned
  detached, the `.pyw` launcher surviving a missing console, and the spec staying
  `console=False`.
- **the installer that would not start** (`AppInstallerPythonRedirector.exe`,
  `0xc0000142`): a *build-machine* fault, not an app fault. Two causes, both now
  impossible to reach silently —
  (1) building with the **Microsoft Store Python alias** (its DLLs come from a restricted
  package folder, so the frozen exe cannot initialise them, and the build "succeeds"
  while the output never opens); (2) a **missing MSVC runtime** on the target PC.
  `tools/preflight_win.py` is now step 0 of `packaging/build.bat` and `build_all.bat`: it
  judges the interpreter (Store alias, 32-bit, too old, no venv), the MSVC runtime, PySide6,
  PyInstaller, Inno Setup, disk space and the build path (OneDrive, long paths), and
  returns **exit 1 with the one action that fixes it** before PyInstaller spends two
  minutes producing something that cannot open.
- **the MSVC runtime is shipped, not assumed**: the spec collects `vcruntime140.dll`,
  `vcruntime140_1.dll`, `msvcp140.dll`, `concrt140.dll` from the build interpreter and
  puts them **next to the exe**, which is the actual cure for `0xc0000142`.
- **`packaging/pyi_rth_arcdesk.py`** — a PyInstaller runtime hook that points
  `stdout`/`stderr` at `%APPDATA%\ArcDesk\logs\arcdesk.log` and starts the log
  **before `run.py` is imported**, so a windowed build that dies in its first second
  leaves a traceback instead of nothing at all.
- **`ArcDeskDiag.bat`** — double-click, no Python, no install: reports the OS, the file
  sizes (a setup exe under 40 MB is a half-download), whether the download is **blocked**
  (Mark of the Web) and offers to unblock it, whether `python` is the **Store alias**,
  whether the MSVC runtime is present, what is already installed, and the App Execution
  Alias state. Writes ArcDeskDiag.txt. It asks before changing anything.
- **`tools/batlint.py`** — `cmd.exe` has no compiler, so a wrong `.bat` prints
  "was unexpected at this time" and carries on. It catches the three silent killers: a
  bare parenthesis in an `echo` **inside a block** (cmd ends the block there), a
  `goto :label` with no label (the script just stops), and — for a diagnostic — any
  `setx`/`reg add`/`set-executionpolicy` in a file that promises to change nothing.
  `tests/test_windows_build.py` feeds it deliberately broken files, so the linter has to
  be able to fail or it is decoration.
- **`TROUBLESHOOT.md`** — every dialog with its cause and its clicks, starting with the
  route that needs no installer at all: extract `ArcDesk-portable.zip`, double-click
  `ArcDesk.exe`.
- **`requirements-build.txt`** — PyInstaller declared as a *build* tool, not a runtime
  dependency, so `tests/test_audit.py` can keep refusing undeclared imports.
- **new `tests/test_windows_build.py`** (10 sections): the Store-alias rules (path,
  base_prefix, redirector name), 32-bit and old-Python refusal, the MSVC collector, the
  spec wiring both the runtime and the hook, both build scripts running the preflight
  **before** PyInstaller, the diagnostic's checks and its "ask first" behaviour, and the
  guide naming the no-installer route first.
- **the green build that shipped a dead exe** (GitHub Actions run #14): every step
  reported success; the installer it produced put a shortcut with **PyInstaller's
  default icon** on the desktop and never opened. The spec step had lasted **2 seconds**
  — a real build takes ~110 — because `packaging/arcdesk.spec` used `sys.path.insert(...)`
  and PyInstaller's spec namespace provides `os` and the build classes but **not `sys`**,
  so it raised `NameError` immediately. `continue-on-error: true` kept the job green, and
  a "fallback build, if the spec was unhappy" then produced a plain `--windowed` exe: no
  `--icon`, no data files, no `ArcDeskVoice.exe`. The installer packed that.
  Fixed in three places, so the same class of bug cannot reach a user again:
  (1) the spec imports `sys` and says why; (2) the workflow has **no** silent fallback —
  the spec build, an output-completeness check (exe + voice exe + `_internal` + icon +
  pages), and a real start test (`ArcDesk.exe --doctor` on the runner, then read
  `arcdesk.log`) must all pass before anything is zipped, and the log is uploaded either
  way; (3) **`tests/test_spec_exec.py`** executes the spec inside PyInstaller's *real*
  namespace — copied from its own source and asserted against it — with the build classes
  stubbed, so a `NameError` is a red test instead of a 2-second green step. It also checks
  what the spec asked for: two exes, `console=False`, onedir, an icon that exists, the
  MSVC runtime, the runtime hook, and the data files a frozen app cannot get otherwise.
- **the second 2-second build (run #15), and the trap behind it**: fixing the missing
  `import sys` exposed a worse one. The spec reached `tools/preflight_win.py` with
  `sys.path.insert(0, "tools")`, and `tools/packaging.py` — *our* checker — then shadowed
  the pip package `packaging` that PyInstaller imports (`import packaging.requirements`),
  so its isolated build subprocess died with
  `ModuleNotFoundError: 'packaging is not a package'`. Reproduced here by instrumenting
  PyInstaller's own child process; the diagnostic line that gave it away was
  `packaging in modules=<module 'packaging' from .../tools/packaging.py>`.
  Fixed by loading the helper with `importlib.util.spec_from_file_location` — **no
  `sys.path` mutation anywhere in the spec or in `run.py --doctor`** — plus three guards:
  `tools/preflight_win.py` now detects a **shadowing** file and fails the build when
  something actually puts that folder on `sys.path` (and says 'latent only' when nothing
  does); `tests/test_spec_exec.py` asserts the spec contains no `sys.path.insert` and that
  `import packaging.requirements` still works after the spec has run; and the workflow's
  start-test now **waits** for the exe to exit and requires the doctor's `RESULT:` line.
  Proven the right way: a full PyInstaller build now completes here (75 s) and the
  packaged binary answers `--doctor` with `RESULT: usable, with 1 warning(s)`.
- **frozen builds stop lying about the silent-spawn scan**: `quiet.covered()` reads the
  sources in a checkout and falls back to the declared list inside a PyInstaller archive,
  so the doctor says `23 of 23 … (compiled build)` instead of a false `[FAIL]`.
- **"installed, but it does not work" (fixed)**: the honest cause was our own visibility
  rule, not a crash. `shadow.enabled` defaulted to **true**, and `--shadow` — the flag the
  Windows boot entry passes — was written into `settings.json`. One boot with Windows, and
  from then on every double-click started a process with no window, no setup card and only
  a tray icon. Fixed four ways: the installer's Desktop / Start Menu shortcuts pass
  `--show`; `--shadow` is now a per-launch flag that `config.save()` strips (underscore
  keys never reach the file); a one-time `shadow` migration (same `user_choice` /
  `migrated_off` shape as the charms rule) corrects old files; and run.py writes its
  decision to the log — `BOOT · the window is shown` / `stealth: …` / `handles: tray=…`.
  Guarded by `tests/test_firstrun.py`, which boots the real entry point four ways —
  `--shadow`, `--show`, **no flags** (a double-click) and an old settings file that says
  "hidden" — and asserts the window state each time, read from the app's own log.
- **the icon existed, was applied, and still showed as a python (found & fixed)**: the
  exe carried our icon (byte-checked) while Explorer drew PyInstaller's. Cause: the `.ico`
  was written by Pillow, which stores *every* frame as PNG. Windows renders 256×256 PNG
  frames fine, but for the 16/32/48 sizes a shortcut asks for it falls back to the file
  type's icon. `tools/make_icon.py` now writes BMP/DIB frames (32-bit BGRA + AND mask) for
  every size below 256 and PNG only for 256 — the layout ICO tools on Windows produce —
  and `tests/test_windows_build.py` asserts the frame layout.
- **the voice was too fast to understand (fixed by measuring the pipeline)**: SAPI was
  being handed one long string at Rate +1. Now: default Rate **-2**, `chunks()` 170
  characters so each utterance is one breath, **SSML** with `<prosody rate>` and a
  180 ms `<break/>` between sentences, and an accent picker that resolves `en-IN` against
  the voices actually installed (`voice.pick_voice`). Settings shows which voice it found;
  "Hear it" speaks at the configured pace.
- **magic mode showed a hologram but not the work (fixed)**: `MagicScreen` now paints a
  work panel from `activity.activity().snapshot()` — request, live step with elapsed
  seconds, and finished steps with timings — polled at 4 Hz and repainting only when the
  activity counter changed.
- **lag (reduced, with numbers)**: the full-screen deck adapts its render quality
  (1920×1080: 19.0 ms → 9.6 ms per frame under load, back to full when the machine
  recovers); `vision`/`uia` are lazy, `smtplib` is lazy; window import cost fell
  367 ms → 232 ms. Measured, not asserted — `tests/test_perf.py` holds the governor and
  the lazy imports.
- **72 tests.**
- **the workflow was simplified** to install → build → zip → upload. A blocking test step
  had cost four builds; the installer is now always produced, with a portable zip as the
  fallback that cannot fail.

## Wave 19 — the dependency lie, and a red run that explains itself

The third CI run got all the way to the tests: **48/60**, and the loudest line was
`test_vision: ModuleNotFoundError: No module named 'PIL'`.

- **`requirements.txt` declared two of the ten packages the app imports.** PySide6 and
  psutil were listed; Pillow, numpy, pypdf, python-docx, openpyxl, python-pptx and mutagen
  were not — because they were installed on the machine this was written on. Anyone
  following the install instructions, and any packaging run, hit a wall the project had
  written down nowhere. All ten are now declared, with the reason each one exists.
- **audit section E2** walks every `import` in the app and FAILS if a third-party module is
  neither declared nor in a documented-optional list (voice engine, GPU clone, scipy…).
  An undeclared dependency is a promise the project cannot keep.
- **`run_all.py` now shows WHY.** A red CI log used to say `FAIL test_reading` and stop.
  Each failing test's last 12 lines print right there, and are written to `.failures/`,
  which the workflow uploads and prints in the run summary. No more asking for screenshots
  to find out what broke.

## Wave 18 — the first real Windows CI run, and what it broke

GitHub's Windows runner ran the suite for the first time and the build went red. Every
failure was real and none of them could appear on Linux:

- **`tests/run_all.py` decoded child output with the platform default.** On Windows that
  is cp1252, so the first test that printed a dash raised `UnicodeDecodeError` inside the
  reader thread, leaving `proc.stdout` as `None` and crashing the runner with
  *"argument of type 'NoneType' is not iterable"* — which then marked three healthy tests
  as FAIL. Now `encoding="utf-8", errors="replace"`, and `proc.stdout or ""` everywhere.
- **Six test files read files with the default encoding too** — `test_catalog` died on
  `GITHUB.md` (UTF-8) with a cp1252 decode error before it could even print a result.
- **`test_backup` wrote a sparse file the size of the disk + 5 GB** to prove a refusal.
  On NTFS that cost 192 s of real runner time. The free space is now injected, no I/O.
- **A plain WAV needed ffmpeg.** `clone.import_reference()` sent any WAV that was not
  already 16-bit mono through ffmpeg; with no ffmpeg (the CI runner) importing your own
  recording failed with *"ffmpeg is needed"* — for a file Python reads fine.
  `_read_pcm_any()` now reads 8/16/32-bit WAVs, averages stereo, resamples and writes the
  24 kHz reference **with no ffmpeg at all**; only real codecs (mp3/mp4/m4a/webm) still
  need it, and the message says which file needs what.
- **`test_holo` graded the frame budget in absolute milliseconds**, which is unfair on a
  shared 2-core runner. It now measures a blank-frame floor first and grades against
  `max(22 ms, 6 x floor)` — machine-relative, so a real regression still fails on any box.
- **CI smoke test read `$LASTEXITCODE` from a windowed exe** (which never sets it), so a
  good build would have been failed by its own check. `Start-Process -PassThru` now reads
  the real exit code, and a `if: failure()` step uploads the log.
- **new audit section F** asserts all of this stays fixed: UTF-8 everywhere, no bare
  `read_text()`, no absolute-limit timing, no `$LASTEXITCODE` on a frozen window.

## Wave 17 — the audit: every promise measured, two more dead things fixed

- **new `tests/test_audit.py`** — the user's one-sentence question turned into 60
  measurements: every Settings control is read on load *and* read by a method that writes
  the config (no dead switches), all 88 tools are callable/described/schema-valid and
  listed in both the docs and the in-app page, every default is either on or off **on
  purpose**, the four modes have four distinct palettes and the HUD still says what it
  promised, and all 98 modules import with no stubs.
- **bug: `effects` was a setting that did nothing.** It was in `config.DEFAULTS` and read
  by nothing in the program — you could set it and nothing would happen. It is now real:
  `theme.tuned()` lays it over the mode, `MainWindow.set_effects()` re-themes a live
  window, and Settings → System → **Visual effects** exposes it (follow the mode / full /
  reduced / off). Measured: `chill` draws at 1.00; "off" is 0.00 and hides the charm
  overlay, which is where the frame cost was.
- **bug: backup refused a small copy on a nearly-full drive.** The space guard reserved a
  flat 200 MB, so a 400 KB backup was refused with *"0.0 GB to copy, 0.2 GB free"*.
  It now refuses only when the copy would not fit or would leave the drive nearly full,
  and prints MB where MB is the truth. Found by `crosscheck`, not by the feature's own
  tests — the tests ran on a roomy disk.
- **doctor** reports the effects intensity alongside the settings, so "why is it still
  slow" has an answer with a number in it.

## Wave 16 — one question at setup, and a voice you teach inside the app

- **`firstrun.OPEN_MODES` + `set_mode()`** — "icon" vs "voice" is one human question that
  sets two real flags (wake + startup) together, refuses to promise a microphone the
  machine cannot use, and derives the current mode from the real flags.
- **setup card** `widgets/welcome.py` asks it in words, and `run.py` arms the ears in the
  same session when the answer is "voice" — no restart, no second pass.
- **Settings → Voice → "How ARC opens"** — the same two options, live; saving stops or
  starts the wake word immediately.
- **new dialog** `widgets/voicelock.py` — three 4-second takes with a live level bar,
  per-take failure messages, "use a WAV file instead", agreement score, and the lock
  switch. The recorder is injectable, which is how it is tested without a microphone.
- **`voiceid.download_model()`** shared by app and CLI; **`run.py --download-voice-model`**;
  the installer offers it post-install (70 MB: 40 MB Vosk + 30 MB speaker model).
- **installer** now asks the same question in `[Tasks]` and documents that the microphone
  stays off until the wake word is enabled.
- **bug fixed with a real model**: sherpa-onnx 1.13.x renamed `compute_embedding` →
  `compute`, which made every embedding `None` and enrolment silently fail.
  Verified end-to-end: same voice **0.70–0.80**, another voice **0.03–0.16**.
- **2 new tests** (`test_openmode.py`, `test_voicelock_gui.py`) → 61 tests
- **the package was actually built and run** (Linux, same spec): two real build bugs found
  and fixed — `ROOT` resolved two parents too high (PyInstaller: *"script run.py not
  found"*, which would have broken `build_all.bat` on Windows too) and `tools/doctor.py`
  missing from the bundle (so `--doctor` died with `ModuleNotFoundError`). Also found
  that `sherpa-onnx` was missing from `requirements-voice.txt`, which would have shipped
  a build where voice lock reports "engine missing" on every machine.
- **new** `packaging/build_all.sh` (Linux/CI mirror of the `.bat`) and
  `.github/workflows/build-windows.yml` (builds the real `ArcDeskSetup.exe` on a Windows
  runner, no Windows PC needed)

## Wave 15 — it moves to another laptop, with the other person's voice

- **new tool** `tools/move.py` — `check` / `pack` / `unpack`. Carries `vault/`, `voice/`
  (clone reference + transcript), `settings.json` and personal context; **strips API keys**
  unless `--with-keys`; **excludes `voiceid/`** (a voice lock is per machine), `models/`
  and logs; refuses to overwrite an existing vault without `--merge` / `--force`; a
  recursive merge keeps both machines' projects; writes a manifest of what was left out
  and why. Zip or folder, both round-trip.
- **bug fixed while testing it**: `config.load()/save()` used a `SETTINGS_PATH` frozen at
  import time, so a process that changed its data folder read the wrong settings. They
  now resolve `settings_path()` on every call — which is what makes `move.py`, portable
  mode and the multi-machine tests honest.
- **`MOVE.md`** — the two-question guide: program on B, data via one zip, models
  re-downloaded, voice lock enrolled fresh.
- **1 new test** (`test_move.py`) → 61 tests.

## Wave 14 — three languages, and clips that are measured

Scope narrowed by the user: *"tamil, hindi, english enough"*. That is now a contract in
code, and the thing that decides clone quality is measured instead of guessed.

- **`clone.PROMISED`** — Tamil → IndicF5, Hindi → IndicF5, English → XTTS. Tested.
  Nine other Indic languages and sixteen XTTS languages stay available as a bonus and
  are never claimed.
- **`clone.analyse()`** — pure-numpy grading: SNR (p90 − p10 of frame RMS), background
  level, clipped-sample %, quiet-frame ratio → `good` / `short` / `workable` / `poor`
  with one sentence of advice. Decodes MP3/M4A/MP4 through the bundled ffmpeg.
- **`tools/clean_voice.py`** — two-pass ffmpeg cleanup (highpass 80 Hz → afftdn →
  loudnorm → edge trim), before/after SNR printed, `--demucs` for a music bed, and
  `--import` to make the result the clone reference in one command.
  Measured on a 50 Hz-hum clip: **SNR 12.2 → 20.6 dB, poor → workable**.
- **`voice_setup.py status`** shows the promise, the reference length, the grade and
  what to fix, instead of a bare "ready".
- **1 new test** (`test_clean.py`, offline; ffmpeg optional) → 61 tests.

## Wave 13 — your voice out, your voice in

Two requests in one message: *"reply en voice-la varanum"* and *"intha laptop-la en
voice-la mattum work aaganum"*.

**Out — speaking in the imported voice**

- **new** `arcdesk/clone.py`: `import_reference()` turns any audio/video into a 24 kHz
  mono reference (ffmpeg, energy VAD, loudness normalisation, **stitching** for edited
  clips, refusal under 4 s of speech, transcript stored for IndicF5).
- **language routing as data, not prose**: `INDIC_LANGS` → IndicF5, `XTTS_LANGS` → XTTS,
  else Piper → SAPI. Tamil is *never* sent to XTTS, which cannot pronounce it.
- **speech chain** in `ai/voice.py`: clone → piper → SAPI, each step returning False
  rather than raising when it cannot do the job.
- **new CLI** `tools/voice_setup.py` (status / import / try / lock-*) and
  **`install_clone.bat`**, which prints every download and its size before asking.

**In — only the enrolled voice may command it**

- **new** `arcdesk/voiceid.py`: sherpa-onnx speaker embeddings, 3 clips → centroid
  fingerprint, self-similarity sets the profile's own threshold, multiple people per
  machine, profiles stored as vectors (never audio) in the app data folder.
- **daemon gate** `--voice-lock` → `_speaker_ok()` checks the *command* audio, logs the
  name and score, and sends "not your voice — ignored" instead of acting.
- **honest failure**: no engine, no profiles, or a broken model all fall back to the
  plain wake word **and say so**. A lock that shuts the owner out is a bug.
- **2 new tests** (`test_clone.py`, `test_voiceid.py`, both offline) → 61 tests.

## Wave 12 — real photographs, not pretend ones

The complaint: *"real elephant picture-oda evlo different... apadiyae irukanum, realistic ah"*.
A vector sketch cannot become a photograph by being drawn better, so this wave adds the only
honest free answer.

- **new module** `arcdesk/photo.py` + **new tool** `photo` (88 tools) — Wikimedia Commons
  public API. No key, no account, no GPU, no upload; ~1 s per picture.
- **licence-aware**: lists photographer, licence and source page on every result, and
  prefers CC0 / public domain over CC BY-SA so reuse later is simple.
- **refuses junk**: a download whose header is not JPEG/PNG/WebP/GIF is rejected instead of
  being saved as `elephant.jpg`; 12 MB ceiling; a non-clobbering file name.
- **shows it on the easel** (`request_photo` → `ArtWindow.show_photo`) and clears the current
  sketch, so "make it purple" cannot pretend to edit a photograph.
- **Lite routing**: `real photo of …`, `picture of …`, `… photo`, Tamil/Hindi animal words
  (`aane`, `haathi`) are mapped before searching; `make me an image of …` still goes to the
  generator, `draw …` still goes to the sketch engine.
- **1 new test** `tests/test_photo.py` (offline, injected API) → 61 tests.


## 2. Reactions — what happens on its own

| Trigger | Reaction | Latency |
|---|---|---|
| `"hey jarvis"` (voice) | 1.9 s cinematic → wallpaper swap → fullscreen ARC world | cinematic is frame-capped, 20 fps overlay |
| `"bye jarvis"` (voice) | wallpaper restored → app hidden (or exits, your setting) | immediate |
| Second `ArcDesk.exe` launched | the running copy is summoned instead of a duplicate opening | < 50 ms socket round-trip |
| `Ctrl+Alt+J` (global) | command palette over any app | hotkey |
| `Ctrl+Alt+Q` (global) | quit, always works, even if the UI is stuck | hotkey |
| `Ctrl+J` (in window) | console | — |
| `Esc` during the cinematic | aborts the arrival, magic mode never opens | — |
| Tray menu | Show · Awaken · Palette · 4 modes · "Is my Windows untouched?" · Quit | — |
| Charms in edit mode | drag, resize, arrange; click-through otherwise | 20 fps |
| Paid brain configured | **refused before any request**, agent falls back to Lite | 0 network calls |
| Any uncaught error | written to `%APPDATA%\ArcDesk\logs\arcdesk.log`, keys scrubbed | — |
| Mic missing but wake enabled | doctor reports FAIL *before* you rely on it | — |
| App killed mid-magic | journal restores wallpaper on next start | — |

---

## 3. Skills — what it can complete end to end

| Skill | Works? | Evidence |
|---|---|---|
| Understand a typed or spoken command offline | ✅ | Lite: **32/32** on the phrase suite |
| Run multi-tool tasks | ✅ up to **4 tool rounds** per request | `MAX_TOOL_ROUNDS = 4` |
| Read the machine and answer about it | ✅ | `system_report` 328 ms real output |
| Control media, volume, brightness, lock, power | ✅ Windows | guarded where destructive |
| Switch its own appearance (4 modes, magic, charms) | ✅ | 20 fps overlay, 83 MB RSS |
| Remember things across sessions | ✅ one notes file (`note` / `read_notes`) | verified write+read |
| Find a file you forgot the path to | ✅ read-only, 4 s cap | verified |
| Use tools it did not ship with | ✅ any MCP stdio server | `mcp__*` routing, tested |
| Work with no key, no model, no internet | ✅ ARC Lite | whole test suite runs offline |
| Switch brains without a code change | ✅ 11 HTTP backends auto-detected | port probe, 250 ms |
| Never spend money by accident | ✅ guard + fallback | tested: paid refused, still answers |

### Where it stops — honestly

| Task | Status | Why |
|---|---|---|
| Draw a picture and edit it by talking | ✅ | 10 subjects, ~3 ms, offline; `COMMANDS.md` §1 |
| "Open notepad and type hello" | ✅ Windows | two tool calls in one sentence, 1.5 s window for the app to appear |
| Switch to / minimize / close a window by name | ✅ Windows · ⚠️ Linux needs `xdotool` | PowerShell `AppActivate` + `ShowWindow` |
| Create, write, copy, rename, read a file | ✅ inside your home folder only | `.bak` kept before any overwrite |
| Run a shell command ARC was told to run | ✅ but **always asks first**, and refuses 15 destructive patterns | `actions.BLOCKED` |
| See what it did while you were out | ✅ journal at `~/ArcDesk/logs/actions.log` | one line per action |
| "What does this error say?" | ✅ | OCR via Tesseract, 1-2 s per screen |
| "Click the Send button" | ✅ by name (accessibility) or by pixels | `ui_act` → `click_text` fallback |
| "Click the blue button in Photoshop" | ✅ if it has a visible label | region detection + OCR per rectangle |
| "Email Raj about the invoice" | ✅ with SMTP configured, password from an env var | confirm-gated |
| "What's on my calendar?" / "add a meeting at 4" | ✅ real `.ics` files, read + write | no account needed |
| "WhatsApp Raj that I'm late" | ⚠️ opens the message; you press send | by design |
| Answer questions about web pages | ✅ with MCP · ❌ alone | enable the **Fetch** server: it reads the page. Without it, `web_search` only opens a tab |
| Read text off your screen | ✅ needs Tesseract installed | `vision.ocr_words`, two-pass + region OCR |
| Click something with **no** visible label (an icon) | ❌ | OCR reads text; icon matching is not built |
| Edit a document / spreadsheet / image / clip | ✅ | `edit_file` — `.docx` find-replace, `.xlsx` cell, `.pptx` text, pdf rotate/split/merge, images, audio, video; **never overwrites** |
| Reach inside another app's UI (click its buttons, read its list) | ❌ | window control is title-level only; no UI automation tree |
| Email | ✅ with your SMTP host + an env-var password (never stored) | `comms.send_email` |
| Calendar | ✅ local `.ics` (read + write); subscribed URL read-only | `comms.list_events` |
| Chat | ⚠️ WhatsApp opens a pre-filled message; you send | no session cookies, deliberately |
| Long conversation memory | ⚠️ | remembers the session, then only what you explicitly noted |
| Reasoning longer than 4 tool rounds | ⚠️ | the loop stops at 4, deliberately, to avoid runaway loops |
| Wake word without `vosk`/`openwakeword` | ⚠️ | app runs, ears do not |
| Weather | ⚠️ | needs internet, off by default (your requirement) |
| A 3B local model giving GPT-level answers | ⚠️ | 3B is fine for commands, weak at essays — that is the ₹0 trade |

---

---

## 4. The file brain — read it, judge it, change it, make it

One reader, one editor, one creator. All three were run against real files built for
the purpose (`tests/test_reading.py` builds a pdf, docx, xlsx, pptx, csv, json, png,
gif, wav and mp4 every run — 43 checks, 0 failures).

| Format | What ARC actually gets | What it does **not** get |
|---|---|---|
| `.txt` `.md` `.py` `.log` | full text, encoding fallback utf-8 → utf-16 → cp1252 → latin-1 | — |
| `.pdf` | per-page text + title/author/page count, 40 000 char cap | **scans without a text layer** → says so and points at OCR; text inside a PDF cannot be rewritten |
| `.docx` | paragraphs, tables, word count | `.doc` is refused with an instruction, not guessed |
| `.xlsx` | every sheet, ≤1 500 rows each, values not formulas | chart images, pivot definitions |
| `.pptx` | slide text + speaker notes | layout, images, animations |
| `.csv` `.tsv` `.json` | sniffed delimiter, row/column counts, JSON structure | — |
| `.png` `.jpg` `.gif` `.webp` | size, mode, EXIF, frame count, **OCR text** (upscaled 2× first) | describing a photo's content without a vision model |
| `.wav` `.mp3` `.m4a` `.flac` | duration, codec, bitrate, channels, tags | **the words** — needs `faster-whisper`; it says so instead of pretending |
| `.mp4` `.mov` `.mkv` | container, codec, resolution, fps, audio track, duration | the words; one frame can be OCR'd on request |

**Summarise, evaluate, improve.** `mode=review` answers the user's three questions in
order with evidence quoted from the file:

```
Review of book.xlsx — xlsx · 5 KB · sheets 2 · rows 4
Verdict: 4 rows of data, 1 gap found
What is there     - 2 sheets · 4 rows
What is missing   - no totals/sums — every table needs a row or column that adds up
What to add       - a 'source' column, so each row says where its numbers came from
```

Spreadsheets get column statistics instead of prose bullets (min → max, mean, total,
blanks, distinct values per column, first sheet only, and it says which sheet).
Documents get sentence-length, date, number, reference and heading checks. Every
observation cites a number that is really in the file, which is what makes it
checkable rather than flattering.

**Editing is always additive.** `edit_file` writes `<name>_<op>_<timestamp>.<ext>`
next to the original and prints the new filename. There is no code path that opens a
user file for writing.

| Kind | Operations |
|---|---|
| image | resize, crop, rotate, flip, greyscale, blur, sharpen, brightness, contrast, text overlay, border, thumbnail, compress, convert |
| audio | trim, convert, normalise, fade in/out, mono, speed, volume |
| video | trim, crop, scale, speed, rotate, → gif, extract audio, frames, thumbnail, burn `.srt` subtitles, watermark, mute, compress |
| text | find & replace, append, prepend |
| docx | find & replace (run-safe), append paragraphs |
| xlsx | set a cell, append a row |
| pptx | find & replace across runs |
| pdf | extract page range, rotate, merge, split |

**Generation — three tiers, no payment anywhere.**

| Tier | What you get | Needs | Measured |
|---|---|---|---|
| 1 · local diffusion | real AI images/video | Automatic1111 on `127.0.0.1:7860` (`--api`) or ComfyUI on `8188` + `ARCDESK_SD_CKPT` | probed live; no backend in this sandbox, so not claimed |
| 2 · offline (default) | generated poster: palette from the colour words in your prompt, arc-reactor motif, typography fitted to the frame | Pillow only | **0.47 s**, deterministic per prompt |
| 2 · offline video | ken-burns clip: N generated stills, slow zoom, cross-concat to h.264 | ffmpeg | **1.8 s** for 3 stills → 12 s 640×360 MP4, 0.3 MB |
| 3 · nothing | explicit instructions for tier 1 | — | — |

Tier 2 labels itself in the same sentence it returns the file: *"this is an offline
graphic poster, not a photo"*. Nothing pretends to be a diffusion model.

---

## 5. Medicine and markets — what is allowed and what is refused

Both domains have one failure mode that matters: a confident sentence that is wrong.
So both are built as **measurement + explicit refusal**, and the refusals are asserted
in tests (`tests/test_health.py` 72 checks, `tests/test_market.py` 33 checks).

| Question | Answer given | Never given |
|---|---|---|
| "chest pain and left arm pain" | EMERGENCY · call 112/108 now · why this pattern is taken seriously | a diagnosis |
| "sore throat for two days" | urgency level, what to track, when to escalate | "it is just viral" |
| "paracetamol how much should I take" | the **published adult label range** + liver warning + "take the packet to a pharmacist" | a dose computed for that person |
| "amoxicillin dose" | prescription-only; the dose is decided by a clinician | a number |
| a medicine outside the verified set | "I do not have verified information for that, and I will not guess" | a plausible guess |
| "kidney function" | what it does, common problems, why, how it is investigated | personal prognosis |

10 medicines with verified adult reference ranges (5 OTC, 5 prescription-only), 6 red-flag
patterns that escalate to emergency, 8 body systems, 6 first-aid guides.

| Market question | Answer given | Never given |
|---|---|---|
| "nifty eppadi" | live quote, 30-day move (existing `stock`/`market_summary`) | — |
| "analyse reliance" | trend from 20/50-day averages, 30-session move, 60-session range position, RSI(14), annualised volatility, worst drawdown | "buy now" |
| "should I buy X" | momentum + volatility + what a position would risk | a recommendation phrased as certainty |
| "position size 100000, 1% risk, 4% stop" | exact units, exposure, exposure % of capital, 2R price — arithmetic only | — |
| "what will it do next week" | a straight line through the past with a ±2σ band, labelled as a line through the past | a prediction sold as knowledge |

Worked example of the arithmetic (not advice):
₹1,00,000 capital, 1 % risk = ₹1,000 budget; entry ₹100 with a ₹96 stop = ₹4 risk per
unit → **250 units**, ₹25,000 exposure (25 % of capital), 2R at ₹108. The number that
matters is the first one: the loss is chosen before the size.

Every market and health reply ends with its disclaimer, and `tests/test_market.py`
fails the build if phrases like *"you should buy"*, *"guaranteed"*, *"risk-free"* or
*"will definitely"* appear in any output.

---

## 6. The hologram deck — the look, and what is behind it

A projected scientific instrument, not a wallpaper: a dotted wireframe planet on the
left, a stack of tilted light rings spiralling into a bright core in the middle, a
numeric data field behind everything, five live instrument panes down the right edge,
two headline byte counts in amber, a palette block, a marquee of measured integers
across the top, a 12-second telemetry spectrum and per-core load bars along the
bottom, and a real log ticker under that. It is the magic screen's surface *and* a
standalone fullscreen view (`holo` tool, tray → **Hologram deck**, or say **"show me
the hologram"**).

**Nothing on it is decoration pretending to be data.** Every figure — the marquee, the
dust, the panes, the headline numbers, the spectrum, the gutter — comes from `psutil`
at 4 Hz or from the running app: CPU %, per-core loads, memory used/total, network
in/out per second, disk used/total/free, swap, load average, disk I/O counters, the
process count and the heaviest processes with their PIDs, uptime, tool count, frame
cap. With no `psutil` every pane prints "no sensor" instead of inventing a value, and
the build fails if a `random()` call appears in the telemetry path.

| Measurement (this sandbox, 2 vCPU, software rasteriser) | Value |
|---|---|
| Paint cost, 1280×720 | **17.9 ms** median, 20.5 ms p90 (30 fps budget is 33 ms) |
| Paint cost, 1600×900 | 23.5 ms median, 26.5 ms p90 |
| Paint cost, 1920×1080 | 30.4 ms median — still inside the frame budget |
| Paint cost, 2560×1440 / 4K | 36 / 40 ms: above 1920 the deck renders internally at 1920 and upscales |
| Cached layers | background+frame, numeric field and panes (4 Hz), data gutter (12 Hz), light-ring stack (20 Hz) |
| GPU | **none used** — QPainter only, so it runs on any Windows 11 laptop |

Design decisions worth knowing:

* **Gaming mode skips it entirely** (`effects < 0.2`): rasterising a starfield behind
  somebody's game is the opposite of a low-footprint promise.
* The magic screen embeds the same renderer through `paint_onto(..., compact=True)`:
  the planet and rings lift and shrink so the app buttons and the input box stay clear.
* **Legibility is tested, not claimed.** `tests/test_holo.py` reads the rendered frame
  back with the app's own OCR engine (the same Tesseract path `look` uses) and requires
  at least three of the five pane labels to be machine-readable; it also checks colour
  spread, lit fraction, a cyan-vs-magenta ratio, that the panes rebuild only when a new
  sample lands, that the grid/ring caches are used, and that no frame costs more than
  33 ms.
* The grain, the flicker and the sweep are labelled projector artefacts, scaled by the
  theme's effect level — they are a deliberate simulation, not an accident.

## 7. Capacity — the real numbers

Fullscreen projection surface: a wireframe globe, an arc-reactor core, four live
telemetry panels, a data-stream gutter, a scan sweep, projector grain and a rising
projection cone. It is the magic screen's surface *and* a standalone view (`holo`
tool, tray → "Hologram deck", or say **"show me the hologram"**).

**Nothing on it is decoration pretending to be data.** Every number is sampled from
this machine with `psutil` at 4 Hz: CPU %, logical cores, memory used/total, network
in/out per second, disk used/total, the process count and the four heaviest
processes. The session card shows real uptime, the real tool count, the real frame
cap. If `psutil` is missing the panel says "no sensor" instead of inventing a value.

| Measurement (this sandbox, 2 vCPU, software rasteriser) | Value |
|---|---|
| Paint cost, 1280×720, one frame | **11.2 ms median**, 15.0 ms p90 (30 fps budget is 33 ms) |
| Paint cost, 1600×900 | 15.4 ms median, 19.5 ms p90 |
| Paint cost, 1920×1080 | 22.2 ms median, 28.2 ms p90 — still inside 30 fps |
| Whole app, embedded, offscreen bench | cpu **1.88% avg**, rss **81.1 MB** |
| Cached layers | starfield/grid/vignette/scanlines, projector glow, cone, data streams (12 Hz), telemetry panels (4 Hz) |
| Cost of the telemetry layer when cached | ~0 ms — it rebuilds only when a new sample lands |
| Peak extra RAM | one screen-sized QPixmap per cached layer, ~4–7 MB total |
| GPU | **none used** — QPainter only, so it runs on any Windows 11 laptop |

Design decisions worth knowing:

* **Gaming mode skips it entirely** (`effects < 0.2`), because rasterising a
  starfield behind somebody's game is the opposite of a low-footprint promise.
* The magic screen embeds the same renderer through `paint_onto(..., compact=True)`
  so there is only one set of pixels to maintain, and the globe lifts so the app
  buttons and the input box stay clear.
* `tests/test_holo.py` reads the pixels back: colour spread, lit fraction, a
  cyan-vs-magenta ratio, and **OCR over the rendered frame** to prove the labels are
  legible (the same Tesseract path `look` uses). It also fails the build if the
  telemetry stops coming from `psutil`, or if a frame costs more than 33 ms.
* The grain and flicker are labelled "projector noise" in the session card — they
  are a deliberate simulation of a projector, not an accident.

## 8. Flaws found in this audit — and what was done

| # | Flaw | Severity | Status |
|---|---|---|---|
| 1 | `find_file` **raised TypeError** in Lite mode — `_call(name, …)` collided with the tool's own `name` parameter, so the whole file-search branch was unreachable | **crash** | **fixed** — parameter renamed, branch now live |
| 2 | Lite missed "go to youtube", "close spotify", "what is using my ram", "find report.docx" | wrong action | **fixed** — 86% → 100% |
| 3 | No way to close an app offline (only the LLM could) | gap | **fixed** — `close_app` intent added |
| 4 | "what is eating my ram" answered with a summary instead of the process list | wrong answer | **fixed** — process intent checked first |
| 5 | Docstring claimed OS-specific tools "declare `platforms`" — most do not, they have Linux/macOS fallbacks (amixer, playerctl, brightnessctl, loginctl) | doc lie | **fixed** — wording corrected, behaviour was already right |
| 6 | The probe had never been run, so none of the above was known | process | **fixed** — `tools/capability.py` + `tests/test_lite_intents.py` now run every time |

### Known limits that are **not** bugs

- `web_search` cannot read results — it is documented as "opens a search", not "answers".
- `timer` / `magic` / `charms` / `arc_mode` need the window open; headless they say so.
- Weather is off by default because it is the only tool that needs the internet.
- Wake word needs an optional 50 MB model — the app never downloads it silently.
- Playback is proven by process, timing and exit status; **nobody has listened to it here** —
  no sound card in the build sandbox. On Windows the OS-handler fallback always exists.
- The media index is read-only and capped at 60,000 files. A bigger library is reported as
  capped, not silently truncated.
- `search_inside` reads text, not pictures: a scanned PDF or a photo of a page is skipped
  unless you ask for the OCR pass. Password-protected files cannot be read, by design.
- `explain` covers **24 named error families**. Anything outside the table is handed back
  with its own text and an honest "I do not recognise this one" — it is a lookup with good
  manners, not a diagnostician.
- Coach answers are frameworks, and they say so on every reply. It is not a therapist and
  will not pretend to be one — the crisis numbers are printed from a constant, not generated.

---

## 9. Running the machine — the rules ARC obeys

Anything that can do what you say can also do what it mishears. So the reach is fenced:

| Rule | Where it lives | What it means |
|---|---|---|
| Data loss needs a human click | `Tool(confirm=True)` on `file_delete`, `run_command`, `close_app`, `power` | the agent loop waits up to 45 s for Yes; the default button is **No** |
| Nothing runs elevated | no `runas`, no `sudo`, no service install | admin tasks are refused, not attempted |
| Writes stay in your home | `actions._safe_path()` | `C:\Windows`, `/etc`, `../../` are refused with a reason |
| Overwrites keep the old version | `file_op("write")` | `<name>.<timestamp>.bak` appears next to the file |
| Destructive commands are refused by pattern | `actions.BLOCKED` (15 patterns) | format, diskpart, bcdedit, reg delete, `rm -rf /`, fork bombs, `curl … \| sh` |
| Output is capped | 1500 chars per tool result, 64 KB per file read | a log file cannot blow the context window |
| Everything is written down | `~/ArcDesk/logs/actions.log` | ask "what did you do" → `action_log` |
| The OS gap is spoken | `windows` / `type_text` / `press` | off-Windows it names the missing package instead of failing silently |

`tests/test_vision.py`, `tests/test_uia.py` and `tests/test_comms.py` cover the eyes
and the people-tools: OCR on a synthetic screenshot, the accessibility→pixels fall
back, `.ics` round trips, and email refusing safely with no password.
`tests/test_actions.py` locks all of it: 8 refused commands, the `.bak`, the home fence,
the read cap, the confirm flags, the key-chord translation, and the nine new Lite verbs.

---

## 10. If you want more capability, this is the order that pays

1. **`sherpa-onnx`** — one project replaces the ears, the voice *and* the wake word
   (`GITHUB.md` §2). Biggest single upgrade.
2. **Kokoro TTS** — the difference between "computer voice" and "someone talking".
3. **A web-fetch tool over MCP** — turns `web_search` from "opens a tab" into
   "reads the page". `npx -y @modelcontextprotocol/server-fetch` is already supported.
4. **`faster-whisper`** — better dictation for accented speech, ~80–300 MB RAM.
5. Nothing else. Everything after this is polish, not capability.
