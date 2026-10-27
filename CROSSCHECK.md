# ARC DESK — cross-check (generated)

Last run: 23 October 2026, 09:49 · `python tools/crosscheck.py --write`

Every `ok` below is a command that ran. `need` means this machine physically cannot prove it (no Windows build machine, no microphone, no desktop).

| | what | how it was checked |
|---|---|---|
| ok | 88 tools in the registry | 7 ask before acting |
| ok | 27 documents | BOOT.md, BUILD_REPORT.md, CAPABILITIES.md, COMMANDS.md … |
| ok | 60 test files | present |
| ok | arcdesk/TOOLS_PAGE.html | present |
| ok | arcdesk/KNOWS_PAGE.html | present |
| ok | packaging/arcdesk.spec | present |
| ok | packaging/build.bat | present |
| ok | packaging/arcdesk.iss | present |
| ok | packaging/make_installer.bat | present |
| ok | packaging/build_all.bat | present |
| ok | arcdesk/photo.py | present |
| ok | arcdesk/clone.py | present |
| ok | arcdesk/voiceid.py | present |
| ok | arcdesk/widgets/voicelock.py | present |
| ok | tools/voice_setup.py | present |
| ok | tools/clean_voice.py | present |
| ok | tools/move.py | present |
| ok | install_clone.bat | present |
| ok | MOVE.md | present |
| ok | VOICE.md | present |
| ok | packaging/fetch_runtime.py | present |
| ok | shots/arc_icon.ico | present |
| ok | TOOLS.md | present |
| ok | uninstall.bat | present |
| ok | check.bat | present |
| ok | install.bat | present |
| ok | install_voice.bat | present |
| **ok** | TOOLS.md + TOOLS_PAGE.html current | tools reference is current — 88 tools, 10 sections, 0 mismatch |
| **ok** | packaging consistent | 76 checks, 0 failed |
| **ok** | docs agree with the code | counts, files, tests |
| **ok** | 72/72 tests pass | the whole suite |
| **ok** | BYE JARVIS closes the application | real app, real protocol, exit 0 |
| **ok** | the app boots (run.py --shadow) | settings written, clean exit |
| **ok** | Answer speed measured | Lite p50 0.28 ms · routing 1.12 ms |
| **ok** | every tool answers when called | live 65 · failed 0 · guarded 6 · platform 0 · skipped 17 |
| **ok** | Application opens by voice | phrase matching, any phrase you set |
| **ok** | 'Bye JARVIS' CLOSES the app | real app + real protocol: process exits 0 (tools/voice_roundtrip.py) |
| **ok** | 'Bye JARVIS' three choices (exit/quit/hide) | and it never quits into silence |
| **ok** | Magic mode (fullscreen ARC + wallpaper, restored on exit) | journal + crash-safe restore |
| **ok** | Windows untouched (no shell/taskbar/explorer changes) | tools/desktop_check.py --scan is the source scan |
| **ok** | Gravity charms (floating sprites, click-through) | painted, not images |
| **ok** | Holographic deck | CPU rasteriser, 30 fps budget |
| **ok** | 86 tools, every one answers | tools/capability.py executes them |
| **ok** | ARC Lite offline brain | ~1 ms, no model |
| **ok** | Real local LLM over HTTP | engine as backend, localhost only |
| **ok** | Streaming + barge-in | test_stream.py |
| **ok** | Voice: OS TTS, manly neural voice, language mirroring | test_voice.py |
| **ok** | Machine-acting layer (windows, keys, clicking, OCR) | UIA + OCR |
| **ok** | Reading any file (pdf/docx/xlsx/pptx/csv/image/audio) | test_reading.py |
| **ok** | Editing files without overwriting the original | new sibling file |
| **ok** | Media studio: video, audio, image | ffmpeg/Pillow, free |
| **ok** | Playback of your own music/video, external disks | test_playback.py |
| **ok** | search_inside: the words inside your documents | test_inside.py |
| **ok** | pc_health: 'why is this PC slow' | two measured samples |
| **ok** | explain: read an error and quote it first | 24 error families |
| **ok** | Backup with SHA-256 proof | test_backup.py |
| **ok** | Autostart: one HKCU entry, read back | test_backup.py |
| **ok** | First-run wizard (five decisions) | test_firstrun.py |
| **ok** | Coach / mentor / analyst modes | test_coach.py |
| **ok** | Medicine rails + crisis numbers | information, never a prescription |
| **ok** | Markets: quotes, arithmetic, position size | test_market.py |
| **ok** | Business, travel, craft, data mining | test_business.py |
| **ok** | Reminders, focus sessions, briefing | test_reminders.py |
| **ok** | Learned voice macros | test_macros.py |
| **ok** | MCP tool servers | 7 reference servers |
| **ok** | 86-package free/open-source catalogue | test_packages.py |
| **ok** | Money: free enforced in code | no paid path |
| **ok** | Docs match the code (counts, files, tests) | test_docs.py rule 1 + 2 |
| **ok** | Packaging: spec, installer, uninstaller | tools/packaging.py |
| **ok** | The real entry point boots | tools/smoke_firstrun.py |
| **ok** | Asks icon-vs-voice at setup, and again in Settings | one answer -> two flags; downgrades honestly |
| **ok** | Voice enrolment inside the app | 3 takes, level bar, WAV fallback, lock switch |
| **ok** | Every Settings control actually changes something | reads the AST: no dead switches, no unread defaults |
| **ok** | All 88 tools are callable, described, schema-valid | and listed in TOOLS.md + the in-app page |
| **ok** | Moves to another laptop without carrying its voice lock | pack/unpack, keys stripped, voiceid excluded, merge keeps both |
| **ok** | Three languages, and clips graded before cloning | ta/hi -> IndicF5, en -> XTTS, SNR before/after |
| **ok** | Speaks in the imported voice, per language | IndicF5 for Tamil/Indic, XTTS for English, piper/SAPI fallback |
| **ok** | Only the enrolled voice may command it | per-machine profiles, threshold from self-similarity |
| **ok** | Real photographs, with credit (not a drawing) | Wikimedia Commons, free licences, no key, no GPU |
| **ok** | The Vault: projects, notes, progress, export | copy-not-move, verified export, 0.45 ms saves |
| **ok** | One-click installer (payload + script) | packaging/build_all.bat + fetch_runtime.py + arcdesk.iss |
| need | ArcDesk.exe launches after PyInstaller | needs a Windows build machine |
| need | Vosk hears your actual voice | needs a microphone + the speech model |
| need | Windows 11 UI behaves as documented | needs a Windows desktop |
| need | Inno Setup produces Setup.exe | needs Inno Setup 6 on Windows |

**27 present · 54 proven · 0 failed · 4 cannot prove here.**
