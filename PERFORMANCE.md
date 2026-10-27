# Arc Desk — performance contract

The rule for this project: **Arc Desk must never be the reason the laptop hangs or lags.**
That is not a nice-to-have, it is a design constraint, so it gets numbers and a test.

## Targets

| Budget | Target | Hard limit | Current |
|---|---|---|---|
| RAM, main app | ≤ 90 MB | 130 MB | ~78 MB |
| RAM, wake daemon (only if armed) | ≤ 150 MB | 220 MB | 60–150 MB, separate PID |
| RAM, charm overlay | +5 MB | +15 MB | +3 MB |
| CPU, 30 fps mode | ≤ 6 % of one core | 12 % | ~5.0 % |
| CPU, paused | ≤ 2 % | 4 % | ~1.6 % |
| Startup to visible window | ≤ 1.5 s | 3 s | ~0.6 s (headless) |
| Disk footprint (packaged folder) | ≤ 60 MB | 90 MB | **298.5 MB built** (86.4 MB compressed, see INSTALL.md) |
| Memory growth per hour | 0 MB | +2 MB | 0 observed |

"One core" matters: on a 4-core laptop, 4.5 % of one core is about 1 % of total CPU.

## Local model, measured (not estimated)

Host: 2 vCPU, 2.0 GB RAM, no GPU, model on CPU. Engine: llama.cpp `b11815` CPU build,
`llama-server --jinja`. Model: **Qwen2.5-1.5B-Instruct Q4_K_M** (1.1 GB on disk).
Phrase: *"what time is it, and how much ram am i using?"* → `tools/live.py`.

| Round | Prompt tokens | Tools offered | Latency | Result |
|---|---|---|---|---|
| cold start (first request, empty KV cache) | 2040 | 26 | **33.7 s** | answered *without* calling a tool, invented "10:30 AM" |
| warm (same system prompt cached) | 2040 | 26 | **2.8–3.6 s** | called `time` + `system_report`, answered correctly |
| warm, trimmed schema set | 1559 | 18 | **2.6–13.6 s** | called both tools in 3/3 runs |
| **ARC Lite, same phrase** | 0 | 0 | **0.5 ms** | called `system_report` directly |

Three things this measurement settled:

1. **Prompt evaluation dominates, not generation.** 2040 tokens of prompt at ~60 tok/s is
   34 s before the model says a word. Generation ran at only 8–10 tok/s, so the answer
   itself was the cheap part. Caching the system prompt is worth more than any tuning.
2. **A small model does not reliably call tools.** Two runs claimed machine facts with no
   tool call at all. That is why `agent.claims_machine_facts()` exists: a reply that states
   a time, CPU, RAM, disk or battery figure without a tool behind it is **discarded** and
   replaced with values ARC measured itself.
3. **Lite is ~6000x faster on phrases it knows.** 0.5 ms versus 3 s is the argument for
   keeping the offline intent layer as the default and treating the model as a bonus.

## How the budget is enforced in code

**1. Single ticker (`arcdesk/ticker.py`)**
Every animation in the app subscribes to one `QTimer`. Frame rate is a single integer that
the current mode sets. Consequences: 30 fps means 30 paint passes for the whole app, not 30
per widget; killing animations is one `set_paused(True)`; a slow laptop can be fixed by
lowering one number.

**2. Cached painting (`arcdesk/widgets/reactor.py`)**
Three layers:
- static (halo, 72 tick marks, 10 coils, rings) — painted once into a `QPixmap`
- glow — painted once, the breathing effect is `setOpacity()`, not a new gradient
- live (3 arcs + 3 orbit dot sprites) — the only per-frame geometry

Building a `QRadialGradient` per frame is the classic Qt CPU trap. We do zero of that
during animation.

**3. No heavy engines**
No QML scene graph, no WebEngine, no OpenGL context, no `QPropertyAnimation` chains, no
stylesheet rewrites inside `paintEvent`. Stylesheets are rebuilt only on a mode change.

**4. Sampling, not polling**
`psutil.cpu_percent(interval=None)` compares against the previous call instead of sleeping
for a second inside the UI thread. Stats tick once per second, never inside `paintEvent`.

**5. Guards (`arcdesk/guard.py`)**
- A fullscreen app (game, presentation, fullscreen video) is in the foreground → animation
  drops to 10 fps automatically. Checked every 10 s, cost ~0.
- On battery power → capped at 20 fps automatically.
- These only lower the ceiling; they never fight your explicit "pause animations" setting.

**6. The AI brain lives outside the process**
This is the single biggest performance decision in the project. A local 3B model inside the
app would add 2–2.5 GB. Instead:
- the LLM is an HTTP request from a worker thread (no model RAM)
- Ollama, if used, is a separate process the OS can page out and you can kill
- ARC Lite, the default, is regex over a dict — effectively free
- replies and tool output are capped (600 chars spoken, 1500 chars back to the model)
- history is trimmed to 12 messages, tool rounds capped at 4
Measured cost of the whole assistant layer: **+4 MB, +0.5 % CPU**.

**8. No QtNetwork, no QtMultimedia**
Both were tempting: `QTcpServer` for the daemon link, `QAudioSource` for the mic. Importing them costs ~4-5 MB each for two sockets and one stream. A plain `socket` on a worker thread (with Qt signals crossing threads, same as the agent) does the same job for ~0. Measured saving: 81.3 MB -> 78.5 MB.

**9. The charm overlay is a sprite field, not a 3D scene**
Gravity Charms could have destroyed the budget. Rules that keep it at ~1.5 % CPU:

| Rule | Why |
|---|---|
| painted sprites, cached per (kind, size, theme) | a charm costs a blit, not a model draw |
| one transparent window for all charms | not one window per object |
| 20 fps hard cap, independent of the app's 30 | full-screen surface, so it repaints less |
| `WindowTransparentForInput` by default | cannot block your icons, taskbar or work |
| max 8 charms, slow easing | nothing loops fast enough to be distracting or expensive |
| hidden entirely in Gaming mode / paused | zero cost when you are not relaxing |

Measured, headless 800x800 full-screen overlay, 4 charms:
`charms on 7.51 %` vs `charms off 5.96 %` → **+1.55 % of one core, +3 MB**.
On a GPU-composited Windows desktop the blits are cheaper than a software raster.

**10. Magic mode is an app window, not a shell replacement**
A fullscreen painted window costs one more surface at the normal frame rate; there is no
process spawned, no shell hook, no compositor trick. And because it hides when you leave, it
costs nothing at rest. If we had replaced Explorer instead, we would have had to run our own
shell 24/7 — a permanent second desktop environment — which is the opposite of a light app.

**11. The ears also live outside the process**
The wake word needs a permanently open microphone and a resident recogniser. That is exactly
the kind of cost that makes an app feel heavy, so it goes in `arc_daemon.py`:

| Part | Where | Typical RAM | Who pays |
|---|---|---|---|
| Arc Desk window (all of the above, incl. charms) | app process | ~83 MB | always |
| Wake daemon + small Vosk model | daemon process | 60–150 MB | only when wake is armed |
| Wake off (`WAKE OFF` pill) | nothing runs | 0 MB | default |

The HUD reports both: `ARC CORE 78 MB · VOICE 84 MB`. Kill the daemon in Task Manager and the
app carries on; the pill just flips to off. Loopback socket + no timers means the app-side
cost of wake is effectively zero when idle.

**7. Bounded memory by construction**
No unbounded caches, no lists that grow per frame, no history buffers. Pixmap caches are keyed
by (size, theme, effect scale) and replaced, never appended.

## Verify it on your own laptop

**Windows Task Manager** → Details → `ArcDesk.exe` (or `python.exe` in dev):
- *Memory (private working set)* is what matters: should sit stable.
- *CPU* should read 0–5 %, and drop to ~0–1 % when you pause animations.

**Or use the built-in meter:** the HUD itself shows `ARC CORE <n> MB` — that is the app
measuring itself, once a second, so you never have to trust a doc.

**Or run the bench:**

```bat
python tools\bench.py --seconds 20 --mode chill
python tools\bench.py --seconds 20 --mode gaming
```

## If it ever gets slower

1. Check the mode. Gaming should read ~2 % CPU; if not, a widget is escaping the ticker.
2. `python tools\bench.py` — if idle CPU is high while animations are paused, a timer is
   still running somewhere; the only timer allowed to touch paint is the ticker.
3. If RAM climbs over hours, we have a cache that is not keyed properly. That is a bug, not
   a tuning issue.
4. Last-resort switch in the config: `"fps_cap": 15` and `"effects"` are honoured globally.

## What Phase 2–4 must not break

Any new feature signs this contract:

- subscribe to `ticker()`, never create your own `QTimer` for animation
- paint static geometry into a pixmap; animate only what moves
- ship no image assets larger than a few KB — prefer painting
- if it can run offscreen/hidden, it must also *stop* running when hidden
- if it needs the network or an AI model, it must be opt-in and run off the UI thread

## Phase 4b re-measurement

After the audit (crash log, single-instance lock, doctor) the idle footprint is unchanged in practice:

```
mode=chill size=1000x668
  rss  avg  79.7-83.0 MB (varies per run)
  cpu  avg  9.53%  (animating) · idle 2.00%
```

The log handler costs one open file descriptor and writes only on an error; the instance lock is a single listening socket on localhost.

## Local model, measured (not estimated)

Llama.cpp server, `Qwen2.5-0.5B-Instruct Q4_K_M`, 2 CPU threads, no GPU, 2 GB RAM
box, 8 tool schemas + `list_tools` in the request:

| Step | Time | Note |
|---|---|---|
| First token, warm server | 0.6 s | 642-token prompt, 21.7 tok/s generation |
| Second round after a tool result | 2.1–2.7 s | 695-token prompt, 14.5 tok/s |
| Same phrase, Lite brain | 0.7 ms | 3 000× faster, and it is the default |

Two things this bench found, both fixed:

* the full 52-tool catalogue is **3 549 tokens** of JSON — a 2 048-token model
  rejects the request outright, so tools are routed (`arcdesk/ai/select.py`);
* a 0.5B model answered "you are using about 1 GB of RAM" after calling only
  `time` — grounding now checks *which* tool ran, not merely that one did.

Reproduce: `python tools/live.py` (needs any OpenAI-compatible server on
localhost), `python tools/bench.py` (GUI cost), `python tests/test_select.py`
(routing).

## Fast path vs model — measured, 8 everyday commands

`python tools/model_bench.py` (fast path on, how it really runs) versus
`--model-only` (the same commands handed to a Qwen2.5-0.5B on 2 CPU threads):

| | Tool accuracy | Median latency |
|---|---|---|
| With the rule-based fast path | **8/8** | **0.0 s** |
| Model alone | 1/8 | 5.3 s |
| Lite brain, same phrase | 8/8 | 0.2 ms |

The model-alone run is instructive rather than embarrassing: it answered
*"18% of 4500 is 762"* (wrong) and *"the Nifty is 24,750"* (invented). Deterministic
commands therefore never reach a language model — `agent._fast_path` asks the rule
matcher first, and only open-ended questions pay the 3–6 s model cost.

## Streaming speech — where the perceived speed comes from

| | Time to first spoken word |
|---|---|
| Serial (answer, then speak) | ~3.7 s on the 0.5B |
| Streaming (speak sentence by sentence) | **0.01 s** in `tests/test_stream.py`, ~0.6 s with the real model |

Measured by a local SSE server in the test suite, so the number is reproducible
without a GPU: `python tests/test_stream.py`.

## The file brain and the new tools — what they cost when idle

Everything heavy is imported *inside* the handler, not at app start, so a session
that never touches a PDF pays nothing for the ability to read one:

| Work | Imported on demand | Measured here |
|---|---|---|
| read a docx / xlsx / pptx | `python-docx`, `openpyxl`, `python-pptx` | 20 ms for a small file |
| read / OCR an image | Pillow + Tesseract (2× upscale first) | 0.3–0.9 s depending on pixels |
| read audio / video | `ffprobe` (a subprocess, never linked into the app) | 15–40 ms |
| edit an image | Pillow | 5.5 ms (resize) |
| build a 12 s motion clip | `ffmpeg` subprocess | 1.8 s, 0.3 MB output |
| generated poster | Pillow only | 0.47 s |
| market analysis | one HTTPS call, ~60 ms | live NIFTY/RELIANCE quotes above |
| health answers | pure Python tables, no network | 1 ms |

The app's own footprint is unchanged by all of this (idle 79.7–83.0 MB), because
none of it runs in the Qt process: readers, editors and ffmpeg are either imported
per call or run as separate binaries.

## The hologram deck

The deck is the most expensive thing Arc Desk draws, so it is measured rather than
described. Paint cost per frame, `QPainter` into a `QImage` on a 2-vCPU sandbox with
a software rasteriser (the same code path a laptop uses when a GPU is unavailable):

| Frame size | median | p90 |
|---|---|---|
| 1280×720 | 17.9 ms | 20.5 ms |
| 1600×900 | 23.5 ms | 26.5 ms |
| 1920×1080 | 30.4 ms | 35.7 ms |
| 2560×1440 | 36.0 ms | 50.9 ms |
| 3840×2160 | 39.9 ms | 44.3 ms |

33 ms is the budget at 30 fps. Everything up to 1080p is rasterised natively; above
1920 px wide the deck renders at 1920 and is enlarged in one nearest-neighbour blit,
which is why 4K costs barely more than 1440p. Three things keep the frame this cheap:
the background/frame, the numeric field and instrument panes, the data gutter and the
light-ring stack are all cached and re-blitted at their own refresh rates (text is the
dominant rasteriser cost), the planet mesh is two paths per ring instead of a pen
change per segment, and the grain is a single texture brush. With the deck embedded in
the magic screen the whole app costs **~1.9% CPU average and ~81 MB RSS** offscreen.
Gaming mode skips the deck altogether (`effects < 0.2`), which makes it free.
