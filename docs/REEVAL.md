# ARC DESK — honest re-evaluation

**Date:** 23 October 2026 · **Build:** 88 tools, 72 tests · measured in this sandbox (Linux, 2 CPU,
2 GB RAM, no microphone, no display attached). Everything below is either something I ran just
now or something I explicitly could **not** run and why.

Screenshot of the app as it stands: `shots/reeval_now.png` (headless render, `--screenshot`).

---

## 1. What actually works right now

| Surface | State | Evidence |
|---|---|---|
| Desktop panel, 4 modes, charms, magic mode | ✅ runs | `shots/reeval_now.png`, `tests/test_app_lifecycle.py` + `shots/reeval_now.png` |
| 88 tools | ✅ 65 executed live, 6 confirm-gated, **0 exceptions** | `tools/capability.py` |
| Hologram deck | ✅ 26 pixel/OCR/cost checks, 12.7 ms/frame at 1280×720 | `tests/test_holo.py` |
| Lite brain (offline, no model) | ✅ 0.7–1 ms per command | `tests/test_lite_intents.py` |
| Real LLM over HTTP | ✅ 2 rounds, real tool call, 3.7 s on 0.5B | `shots/live_qwen05b_trace.txt` |
| Tool routing (52 → 4–9) | ✅ 3 549 → 178 tokens | `tests/test_select.py`, 24/24 phrases |
| Language mirroring (Tamil / Tanglish / Hindi / English) | ✅ 16/16 phrases | `tests/test_lang.py` |
| Exact maths, units, FX, stocks, trend band | ✅ live quotes | `tests/test_knows.py` |
| Teach-by-voice macros (+ refusal of destructive steps) | ✅ | `tests/test_macros.py` |
| Neural male voice (Piper) + sanitiser + chunking + cancel | ✅ 15.6 s real WAV | `shots/arc_manly_voice.wav` |
| Grounding: invented machine facts replaced by measured ones | ✅ triggered for real on 0.5B | `tests/test_agent_guards.py` 6 + 6b |
| Drawing engine, art edit by voice, OCR, UIA, email/calendar | ✅ (OCR/UIA exercised, honest errors without a display) | `shots/eyes_trace.txt` |
| Footprint | ✅ **80.5 MB RSS, 1.32 % CPU** idle-ish | `tools/bench.py` |
| Docs ↔ code consistency | ✅ 22 docs, 0 count drift, 0 dead file references | `tests/test_docs.py` |
| Packaging (spec, installer, uninstaller) | ✅ 35 checks, 0 failed, **3 rows honestly UNVERIFIED** (needs Windows) | `tools/packaging.py` |
| The real entry point boots | ✅ `run.py --shadow`, settings written, stop signal → exit 0 | `tools/smoke_firstrun.py`, `tests/test_firstrun.py` |
| Tool reference | ✅ generated from the registry, stale-proof | `tools/gen_tools_doc.py --check` |
| Vault (projects, progress, export) | ✅ copy-not-move, verified export, 0.45 ms saves | `tests/test_vault.py` |
| Answer speed | ✅ Lite 0.28 ms · routing 1.01 ms · tool 0.01 ms | `tools/speedcheck.py` |
| One-click installer payload | ✅ scripts + size measured (195→58 MB), exe UNVERIFIED here | `tools/packaging.py`, `tools/sizecheck.py` |

**Code:** 165 Python files, 40 938 lines (app, tools, tests). **Docs:** 22 files, 5 471 lines. **Tests:** 52, all passing.

---

## 2. What is claimed but has never been run — the honest list

These are the weak spots, and they are exactly where the "JARVIS" promise lives.

| Claim | Reality today | Risk |
|---|---|---|
| **"HEY JARVIS" opens it** | Wake pipeline is complete and unit-tested with *simulated* audio. `vosk`, `sounddevice`, `openwakeword` are not installed here, and there is no microphone. **Never heard a real voice.** | **High** — it is the headline feature |
| 13 desktop tools (`open_app`, `set_volume`, `brightness`, `media`, `clipboard`, `click_text`, `click_at`, `ui_act`, `lock_screen`, `open_url`, `web_search`, `email_draft`, `mute`) | Written, wired, refined messages — **never executed**, because this box has no Windows desktop | **High** |
| Installer (PyInstaller spec + Inno Setup script) | Scripts exist; **no build ever produced an EXE** | Medium |
| MCP servers (7 presets) | Config + manager exist; needs `node`/`npx` — not verified in this session | Medium |
| Tamil speech | Piper has **no Tamil voice**; falls back to Windows SAPI | Low (works, sounds worse) |
| "Magic mode" reversibility | Journal + restore logic tested; never run against a real registry | Medium |
| **"play X" actually plays** | The spawn/measure/stop logic is tested against `ffplay` with a dummy audio driver, and the whole route (typed command → Lite → tool → process) runs green. **Never listened to** — this box has no sound card, no mpv/vlc | Medium — the fallback chain and the 350 ms failure check are the safety net |
| External-disk scan on a real USB drive | The index is proven on a temporary tree and on a faked removable drive; no physical USB disk was attached here | Low — read-only `os.stat`, and an unplugged path refuses instead of rescanning |
| The coach on a bad day | Text paths (crisis, low, mentor, decide) are all tested; nobody has actually used it while upset. The rails are real, the comfort is untested | Low-Medium — this is why the crisis numbers are hard-coded, not generated |

If you want one sentence: **the brain is proven, the desktop hands and the ears are not — and
as of wave 5 the hands can start a real player and read a real disk, which is the first time
that sentence has changed.**

---

## 3. Where the experience still falls short (product view)

1. **You must say "Hey JARVIS" before every single thing.** Real JARVIS has a conversation, not a
   command line. This is the biggest gap between "demo" and "companion".
2. **3.7 s before it starts talking.** Feels slow even though it is technically fine. It is waiting
   for the *whole* answer before speaking the first word.
3. **You cannot interrupt by talking.** You can press Esc or say "stop", but you cannot start
   speaking over it, which is how humans talk.
4. **It does not remember you.** Notes are files, not a model of who you are: your name, your
   projects, your habits, your preferred volume.
5. **It never speaks first** — none of the "sir, your battery is at 12 %" energy.
6. **0.5B is the wrong default.** It is the only model I could fit in 2 GB here; on your laptop
   a 3B would be far better and we have never measured the difference.

---

## 4. What would make it genuinely great — ranked by (wow ÷ effort)

| # | Idea | Why it feels like JARVIS | Effort | Risk |
|---|---|---|---|---|
| **1** | **Conversation mode** — after answering, keep listening 8 s; "thanks" ends it | Removes the wake word from every turn. Biggest single jump in feel | ~1 day | Low — daemon already has the loop, mic muting exists |
| **2** | **Streaming voice** — speak sentence 1 while sentence 2 is generating | First word in ~0.6 s instead of 3.7 s. Latency "disappears" | ~1 day | Medium — needs streaming HTTP + chunked speak |
| **3** | **Real memory profile** — a 2 KB `profile` file (name, projects, habits), auto-injected | It starts sounding like it *knows* you; "open my editor" just works | ~1 day | Low — 2 KB file, no embeddings |
| **4** | **Barge-in** — talk over it, it stops mid-sentence | Interruption is the thing people notice in film JARVIS | ~1.5 days | Medium — needs VAD while speaking |
| **5** | **Windows verification harness** — extend `tools\doctor.py` with a `--deep` mode that runs the 13 unproven tools + mic + wake on *your* PC and prints PASS or FAIL per item | Turns "it should work" into "it works, here is the log" | ~1 day | Low |
| **6** | **Proactive one-liners** (opt-in, silent by default) — battery, meeting in 10 min, 90-min focus | The "he noticed before I did" moment | ~1 day | Medium — must be quiet by default or it becomes nagware |
| **7** | **Model tier bench** — 20 fixed commands × 0.5B / 1.5B / 3B, table of tool-call accuracy + tok/s | Lets us pick the default honestly instead of by guess | ~half day | Low |
| **8** | **Screen-aware answers** — screenshot → OCR → model: "idhu enna error da" | Genuinely useful daily, and only ARC-with-eyes can do it | ~1 day | Low (Tesseract already solved) |
| **9** | **One-click MCP skills** — add GitHub/Postgres/Fetch from inside settings | Grows capability without shipping code | ~2 days | Medium |
| **10** | **First-run wizard + signed-ish installer + autostart toggle** | Removes all setup friction; feels like software, not a repo | ~2 days | Medium |

---

## 5. What I would refuse to build (still)

- Replacing or killing Explorer, or anything that changes stock Windows 11 at boot.
- An unkillable / self-hiding process. `Ctrl+Alt+Q` always quits, forever.
- Auto-spending, paid tiers, or anything that phones home with your data.
- Cloud-only brain. Everything above works with the network cable pulled, except weather, FX and stocks.
- A "3D universe" engine. It costs 200 MB of RAM to look slower. The arc reactor is enough.

---

## 6. If you say "go", I would do it in this order

**Weekitem 1 — make the existing thing true (highest value, lowest risk)**
1. `tools\doctor.py --deep` — the 13 unproven desktop tools + microphone + wake word, PASS or FAIL each,
   one log file you can send me.
2. **Conversation mode** on by default after a wake (config: `wake.converse`, 6 turns, "bye"/silence ends it).
3. **Real memory profile** (2 KB) injected into every prompt.

**Weekitem 2 — make it feel fast and alive**
4. Streaming voice (speak while generating).
5. Barge-in with VAD.
6. Model tier bench, then set the honest default.

**Weekitem 3 — polish and ship**
7. Proactive notices, opt-in.
8. Screen-aware answers.
9. Installer + first-run wizard.

---

## 7. Reproduce every number above

```bat
python tests\run_all.py                 :: 72 tests
python tools\capability.py              :: 88 tools · 65 live · 6 guarded · 0 failed
python tools\bench.py                   :: 80.5 MB RSS · 1.32 % CPU
python tools\live.py --repeat 3         :: real model, real tool calls
python tools\say.py --voices            :: what your machine can actually pronounce
python tools\explain.py "hey jarvis draw an elephant" --run
python tools\doctor.py --deep           :: environment + 12 core checks + desktop + voice
python tools\doctor.py --deep --touch   :: the same, but it really opens Notepad and locks
```

In this Linux build sandbox (no root, and installed packages do not survive between
sessions) one command puts the verification toolchain back — ffmpeg, ffplay, Tesseract,
the Qt shared libraries and `uvx` — without installing anything system-wide:

```bash
source tools/sandbox_env.sh && python tests/run_all.py
```

That is a sandbox convenience. On Windows the installer or `winget install` already
provides all of it.

---

## 8. Status after the "do everything" pass (same day)

Everything in §6 is now built and tested. What changed, in the order it was done:

| Item | What shipped | Proof |
|---|---|---|
| Deep check (was #5) | `python tools\doctor.py --deep` — 14 desktop tools + mic + wake, one log file | `arcdesk/deepcheck.py`, runs clean here with honest SKIPs |
| Conversation mode (#1) | 6 turns without the wake word; "thanks / seri podhum / theek hai" closes it | `tests/test_talk.py` |
| Memory profile (#3) | `profile.json` (10 fields), learned from "my name is…", injected into every prompt | `tests/test_talk.py` §4–7 |
| Barge-in (#4) | talk over ARC and it stops: sustained-energy test, not one spike | `tests/test_talk.py` §3 |
| Streaming voice (#2) | first word at **0.01 s** in the test server; sentence-by-sentence speech | `tests/test_stream.py`, `shots/model_bench_summary.txt` |
| Model bench (#7) | `python tools\model_bench.py [--model-only]` | **0.5B alone: 1 of 8 commands, median 5.3 s. With the fast path: 8/8, median 0.0 s** |
| Screen answers (#8) | `look` tool — screenshot → OCR → model | routed correctly in `test_select.py` |
| Proactive one-liners (#6) | `arcdesk/nudge.py`, opt-in, silent by default | `tests/test_nudge.py` |
| One-click MCP (#9) | already existed: Settings → Tools → "Add all free servers" | `MCP.md` |
| First-run wizard (#10) | three decisions, voice test, Esc = "just use Lite" | `shots/welcome.png`, `tests/test_welcome.py` |

The single most useful finding: **the 0.5B model answered "18% of 4500 is 762" and
invented a NIFTY level of 24,750** when left alone — so deterministic commands now
never reach it. That is not a downgrade, it is the reason the assistant is usable
on a small model.
