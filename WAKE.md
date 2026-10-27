# Wake word — "Hey JARVIS"

Off by default. Nothing listens to your microphone until you turn it on.

The phrase is **yours to change**: it is a config value, not a trained model, so
`hey jarvis`, `wake up arc`, `ei macha` or anything else works with no download and no
retraining.

## Why it runs in a separate process

Continuous listening needs a microphone buffer and a recogniser resident. That is 60–150 MB
and a permanently open audio device. Putting it inside Arc Desk would break the RAM budget
the whole project is built around.

```
  ┌───────────────────────────┐        loopback TCP 8765        ┌────────────────────────┐
  │  Arc Desk (main app)      │  <── JSON lines ──             │  arc_daemon.py         │
  │  ~76 MB · UI + brain loop │                                │  mic + Vosk (~80 MB)   │
  │  WakeServer (QTcpServer)  │  ──{"event":"wake"} ──>         │  its own PID           │
  └───────────────────────────┘                                └────────────────────────┘
                                                     kill it any time, app keeps running
```

The daemon **connects to the app**, not the other way round. So the daemon can crash, be
reinstalled, or simply not be running — the app never notices and never blocks.

## Install (once, ~1 minute)

```bat
install_voice.bat
```

That installs the backend engines only: `vosk`, `sounddevice` (~25 MB, no model).
Then download the 40 MB speech model:

```bat
.venv\Scripts\python arc_daemon.py --download-model
```

## Turn it on

1. Click the **WAKE OFF** pill in the header, or `⋯ → Wake word`.
2. It becomes `WAKE · HEY JARVIS` and the daemon starts.
3. Say: **"Hey Jarvis"** → the app pops up, the robot's rings expand → say your command
   within 7 seconds → ARC answers and speaks.

Check it without a microphone first: `⋯ → Test wake word (no mic)`.

## How a spoken command is understood

Five stages, each one able to *stop* the sentence before it reaches the next:

| # | Stage | Code | What it decides |
|---|---|---|---|
| 1 | **Mic** | `arc_daemon.py` `Mic` | 16 kHz mono, 30 ms chunks. Silence (RMS below `SILENCE_RMS`) costs nothing. |
| 2 | **Wake** | `arcdesk/wake/phrases.py` `which()` | exit phrase checked **first**, then the wake phrase. Neither → the sentence is thrown away. |
| 3 | **Command window** | `capture_command()` | opens for `command_seconds` (7 s default), closes after **1.1 s of silence** following speech. |
| 4 | **Transcribe** | Vosk | streaming partials + a final result, fully offline. |
| 5 | **Understand → act** | `arcdesk/ai/lite.py` or `~agent.py` | Lite: regex intents → the same tool registry. Brain: function calling, up to 4 tool rounds. |

The reply goes back over the same IPC link as `text`; ARC speaks it with SAPI only if
AI voice is on, and always writes it to the console and the reply bubble.

### Matching is deliberately looser than string equality

A recogniser does not return the words you said, it returns *its guess*, and that guess
changes with your accent, your microphone and the room. So `contains_phrase()` tries, in
order: exact substring → every word present → word-by-word fuzzy → greeting dropped
("jervis", "a jarvis", "hey service"). `difflib` ratio ≥ 0.78 and words of 4+ letters only,
so `hey` alone can never wake it.

The exit phrase is checked before the wake phrase for the obvious reason: if fuzzy matching
were applied naively, `bye jarvis` would read as `hey jarvis` and the first word you said
would open the app you were trying to close. `tests/test_phrases.py` locks all of these
edges (26 checks, no microphone needed). `--no-fuzzy` on the daemon disables steps 3–4 if
you would rather miss a wake than ever get a false one.

### See it decide

```bat
python tools\explain.py "hey jarvis draw an elephant" --run --then "hey jarvis make it purple"
python tools\explain.py --misheard
```

The tracer prints every stage with the real functions, and shows the first stage that
said no. When ARC "does not listen", that is the fastest way to find out whether it was the
wake word, the transcription, the intent or the tool.

### After it understands: think, act, answer

Understanding produces *text*. Turning text into action is the agent loop
(`arcdesk/ai/agent.py`), and it is deliberately boring:

```
prompt  = persona + one-line machine context + last 12 messages
         + tool schemas (26 built-in, plus whatever MCP servers you enabled)
round 1 = model replies with tool calls or with an answer
          → each call goes through agent._execute()
             · spec.confirm?  → QMessageBox, 45 s wait, "No" is the default
             · otherwise      → tools.call(name, args)
             · result capped at 1500 chars, appended as a `tool` message
round 2 = model reasons over the real result and answers
          capped at 4 tool rounds, then it says it went in circles
```

Three properties matter here:

- **The model cannot touch the machine.** It can only name a tool and pass JSON. Every
  guard — confirmation, cost blocking, result caps — sits outside the model, so a
  misbehaving or hallucinating model cannot skip them.
- **Round 2 sees ground truth.** Tool output is appended as a message rather than
  remembered, so the answer is built from what actually happened. If a tool fails, the
  failure is what the model reads, and the persona rules forbid claiming success.
- **Lite is the same registry.** `lite.respond()` matches intents with regex and emits the
  identical tool-call shape, so an offline install gets the same actions with no model.

The answer then goes to four places from one string (`window._on_reply`): the console
transcript, the reactor animation (SPEAKING for 2.6 s), the magic-screen status strip, and
Windows SAPI speech — but only if AI voice is on. The palette mirrors the console, and
`add_tool()` logs every call with its arguments and result, so what you heard, what you
saw and what ran cannot disagree.

```bat
python tools\think.py                                   :: the whole loop, traced
python tools\think.py "how much ram am i using, and draw me a cat"
python tools\think.py --confirm "shut down the pc"      :: the permission gate
```

`tools/think.py` runs the **real** agent loop with a scripted model, so you can read every
message that would go over the wire without needing an API key or an internet connection.
`tests/test_agent_guards.py` locks the four edges: the loop stops, a denial is respected,
a huge result is truncated, an invented tool name is an error.

### Speaking the answer

`arcdesk/ai/voice.py` — the engine is whatever the OS already has (SAPI on Windows,
`say` on macOS, `espeak-ng` on Linux), so it costs 0 MB of our RAM and ships nothing.

```
say(text)
  sanitise()   markdown, `code`, URLs, #hex, file paths → spoken words
               "arc_elephant_1792666838.png" → "the file arc elephant"
  chunks()     ~220 chars, split at sentence ends, never mid-word
  worker       speaks chunk 1, 2, 3… checking a generation counter between each
```

- **A new sentence cancels the old one.** `speak()` bumps a counter; the old worker sees a
  stale number and returns. `stop()` does the same without starting a replacement, so there
  is never a queue of stale replies talking over each other.
- **Language follows the text.** Tamil script → `-v ta`, Devanagari → `-v hi`, otherwise
  the engine default. `ai.voice_name` pins a specific SAPI voice.
- **The written form and the spoken form differ on purpose.** The bubble keeps the exact
  path and hex colour; the voice hears "the file arc elephant" and "that colour".

`tests/test_voice.py` locks the sanitiser, the chunker, the cancel and the stop phrases.

```bat
python tools\say.py --voices
python tools\say.py "drew an elephant" --wav out.wav     :: render a file instead
python tools\say.py --cancel                            :: prove the cancel works
```

### The honesty guard

A spoken assistant that invents your RAM usage is worse than one that says nothing. So a
reply that contains a machine fact (time, CPU, RAM, disk, battery, a percentage, a clock
time) is only accepted if a tool actually ran. If the model answered without calling
anything, `agent._grounded_truth()` measures it, logs those tool calls, and replaces the
sentence — telling you plainly that the model's numbers were not used.
This was not hypothetical: a real 1.5B local model answered "the time is 10:00 AM, your
system is using 0% of RAM" without touching a tool. See `PERFORMANCE.md`.

### Honest limits

```
- The wake word needs `vosk` or `openwakeword` installed and is OFF by default; the typed
  path (Ctrl+J, Ctrl+Alt+J, the easel line, `run.py --ask`) needs none of it.
- Vosk small-model accuracy is fine for "open notepad", weak for long dictation.
```

## Change the phrase

`⋯ → Assistant setup` does not cover this yet; edit the config:

```
%APPDATA%\ArcDesk\settings.json
```

```json
"wake": {
  "enabled": true,
  "phrase": "hey jarvis",
  "engine": "auto",
  "port": 8765,
  "command_seconds": 7,
  "autostart_daemon": true
}
```

Restart Arc Desk. That is the whole custom-wake-word story — the recogniser is given your
phrase as a grammar, so it only listens for that phrase.

## Which engine is used

| Engine | Trigger | Pros | Cons |
|---|---|---|---|
| **Vosk grammar** (default) | any phrase you type | zero training, tiny, offline | slightly more false positives on short phrases |
| **openWakeWord** | `hey jarvis` (pretrained) | very few false positives | only its pretrained phrases; needs `onnxruntime` |

`"engine": "auto"` uses openWakeWord when the phrase contains "jarvis", otherwise Vosk.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no microphone access` | `pip install sounddevice` in the venv; check Windows mic privacy settings |
| `model missing` | `python arc_daemon.py --download-model` |
| nothing triggers | `python arc_daemon.py --level` shows a mic meter — if it stays flat, Windows is blocking the mic |
| triggers on everything | use a longer phrase (3+ syllables) or switch `"engine": "openwakeword"` |
| `Arc Desk is not listening` | start the app first; the daemon needs it as the receiver |
| wrong words recognised | speak 1–2 s after the wake word, `command_seconds` higher if you ramble |

## Honest limits

- Accuracy of the *command* is "small model" accuracy: good for `open notepad`, weaker for
  long dictation. Bigger Vosk models or `faster-whisper` improve it at a RAM cost.
- English model only by default; Vosk has models for `hi` (Hindi) and others — swap
  `--model-dir` and the same phrase logic works.
- The daemon is not hardened against a hostile local process connecting to port 8765. It is
  loopback-only and single-user; do not expose it to a network.
- Freezing the app into an .exe does not freeze the daemon yet (see `ROADMAP.md`).

## Answering — how it decides what to say

The input pipeline above ends with text. This is what happens to that text.

```
text ──► lite intents (offline, ~0 ms)  ──hit──► say it, done
      │
      └─► language mirror      arcdesk/lang.py
            detect()  ta | tanglish | hi | hinglish | en   (script first, then
            weighted romanised markers — one shared word is never enough)
            mirror()  returns the code + one style line for the system prompt,
            so the model replies Tamil-in-Tamil-script, Tanglish-in-Latin, etc.
      │
      ├─► taught macro?        arcdesk/macros.py   "when I say work mode, …"
      │        safe steps only: open_app, set_volume, note, draw, screenshot…
      │        destructive tools are refused *at teach time*, not run time
      │
      ├─► does a tool answer this better than a model?
      │        arcdesk/knows.py — calc, convert, rates, stock, project.
      │        A model guesses "18% of 4500"; knows.py computes 810.
      │        Quotes end with "information, not investment advice", and a
      │        projection is labelled a straight line through past prices.
      │
      └─► the model (Lite rules, or Ollama / llama.cpp / LM Studio / LocalAI /
              OpenAI-compatible). Tools are declared to it; it picks one; the
              result is fed back; two rounds maximum; confirm-gated tools ask
              the UI first and a "no" is final.

      ──► voice out: markdown stripped, numbers and symbols spoken, long replies
          split at sentence boundaries, a new reply cancels the old one mid-sentence.
```

Every arrow above is covered by a test: `test_lang.py`, `test_knows.py`,
`test_macros.py`, `test_agent_loop.py`, `test_voice.py`. To watch the whole chain
on your own phrase without a microphone:

```bat
python tools\think.py "enna panra macha"
python tools\think.py --tools "18% of 4500 and nifty price" --show-request
```

## After the wake word — conversation, not a command line

```
"hey jarvis" ──► wake ──► listen (7 s window) ──► answer ──► speak
                                    ▲                       │
                                    └──── conversation mode ┘   (up to 6 turns,
                                          no wake word needed)   "thanks" ends it)

while ARC speaks:  mic is muted for transcription, still measured for energy
                   └─ you talk over it → barge-in → speech stops, your turn starts
```

* **Ending it** — "thanks", "that's all", "seri podhum", "theek hai", "chalo", "bas".
  Silence for one turn ends it too; nothing keeps the microphone open after that.
* **Interrupting it** — four consecutive loud frames (~1.2 s of speech). One bang,
  a door, or a chair creak is ignored on purpose; `arcdesk/wake/talk.py` is the
  whole rule, and it adapts its threshold to the noise floor of your room.
* **What it remembers** — `profile.json`, ten fields, filled by plain sentences
  ("my name is…", "i use…", "reply in…"). It is read into the prompt, never executed.
* **Typed commands skip all of this** — the console (Ctrl+J) and the palette
  (Ctrl+Alt+J) go straight to the agent, so a dead microphone never blocks you.

Tests: `tests/test_talk.py` (the three rules), `tests/test_stream.py` (speech while
generating), `tests/test_wake_pipeline.py` (the daemon handshake).
