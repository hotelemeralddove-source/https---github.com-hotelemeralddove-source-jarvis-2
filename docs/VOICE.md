# Your voice, and only your voice

Two different things were asked for in the same breath, so they get two different
answers — and neither of them is pretending to be more than it is.

| Question | Answer | Where |
|---|---|---|
| "ARC should **speak in my voice**" | voice **cloning**: a local model copies your tone from a 10 s clip | `arcdesk/clone.py` |
| "ARC should reply in **whatever language I spoke**" | already done — the reply language follows your words | `arcdesk/lang.py` |
| "Only **my** voice should wake it on this laptop" | speaker verification: a fingerprint of your voice, enrolled here | `arcdesk/voiceid.py` |
| "On another laptop, a **different person**" | profiles live per machine, so laptop B starts empty | `arcdesk/voiceid.py` |

---

## 1. Speak in the uploaded voice

```bat
python tools\voice_setup.py import  "C:\Users\you\Downloads\clip.mp4"
python tools\voice_setup.py try     "vanakkam macha, ellam ready"
```

`import` does the unglamorous work that decides whether a clone sounds like you:

* converts any audio or video (ffmpeg, already bundled) to **24 kHz mono 16-bit**;
* finds the **actual speech** with an energy VAD — an edited clip with music gaps is
  **stitched** into one usable reference instead of being refused;
* normalises loudness and keeps every peak below 0 dBFS;
* refuses a clip that has less than 4 s of speech, and says how much it found;
* stores the reference **and its transcript** (`%APPDATA%\ArcDesk\voice\reference.txt`), because IndicF5 needs
  to know which words it is hearing.

Nothing is uploaded anywhere. The reference stays in `%APPDATA%\ArcDesk\voice\`.

### The scope: **Tamil, Hindi, English** — those three are the promise

```python
PROMISED = {"ta": ("indicf5", "Tamil"), "hi": ("indicf5", "Hindi"), "en": ("xtts", "English")}
```

Three languages, three tested routes, nothing vague. The other nine Indic languages
and the other sixteen XTTS languages usually work and are still in the table below as a
**bonus** — they are never claimed, because a language that half-works in a voice you
cannot understand is worse than a clear "not supported".

### Which engine speaks which language — and why

| Language you speak | Engine | Clones? | Reality |
|---|---|---|---|
| **Tamil, Hindi, Kannada, Telugu, Malayalam, Bengali, Gujarati, Marathi, Punjabi, Odia, Assamese** | **IndicF5** (AI4Bharat, 330 M) | yes | needs a GPU to be quick; on CPU it is slow but honest |
| English, Spanish, French, German, Italian, Portuguese, Polish, Turkish, Russian, Dutch, Czech, Arabic, Chinese, Japanese, Hungarian, Korean | **XTTS-v2** (Coqui) | yes | CPU is possible |
| anything, when no clone engine is installed | **Piper** | no | *real* language, *different* voice — and it says so |
| last resort | Windows SAPI | no | instant, robotic |

**The awkward truth:** **XTTS cannot speak Tamil.** Neither can Chatterbox, the other
MIT-licensed clone model. If IndicF5 is not installed, ARC will speak Tamil in a Piper
voice rather than have your cloned English voice mispronounce Tamil. That is a
deliberate choice: a wrong voice is better than a wrong language.

### Before you clone: is the clip good enough?

```bat
python tools\clean_voice.py "clip.mp3"
python tools\clean_voice.py "clip.mp3" --import --transcript "the words it says"
```

`clone.analyse()` grades a clip with numbers instead of opinions:

| grade | means | what to do |
|---|---|---|
| `good` | SNR ≥ 25 dB, 8–20 s, no clipping | clone it |
| `short` | clean voice, under 8 s | add a few seconds — this is the one your 4.5 s clips got |
| `workable` | SNR 15–25 dB or clipped a little | run `clean_voice.py` first |
| `poor` | noisy, clipped or unusable | record again, in a quieter room |

`clean_voice.py` runs highpass (kills 50 Hz mains hum and desk thumps), spectral denoise
(fan, hiss, air-con), edge trimming and loudness normalisation, then **measures the SNR
again** and prints before/after. Measured on a synthetic 50 Hz-hum clip: **SNR 12.2 →
20.6 dB, grade poor → workable**. On a music bed it cannot help — music and voice share
the spectrum — and it says so, pointing at `demucs` if it is installed.

### Licence, stated plainly

* **IndicF5** — code MIT; the model's own terms say: *clone only voices you have
  permission to use.* Your own voice, or a person who said yes. Not a film star.
* **XTTS-v2** — CPML: **personal / non-commercial only**. Fine for your own machine;
  it is not something you can ship inside a paid product.
* **Piper** — GPL-3.0 fork, commercially usable with the usual copyleft conditions.

Only clone a voice you have the right to clone. A cloned voice saying something the
person never said is the one genuinely harmful thing this feature can do.

---

## 1b. Two different voices — Settings → Voice → **Voices…**

One screen, two lists. They answer two different questions and they are not the same list:

| | question | who can be on it |
|---|---|---|
| **1 · Who may command it** | whose voice is obeyed? | **any number of people** — you, your family. Add a recording of each. |
| **2 · The voice ARC answers in** | which voice speaks the reply? | **any voice you have a recording of** — yours, or a completely different one (a film voice, a friend's, whoever said yes). |

So: *command in your voice, reply in the voice you chose*. That is the point — and the
reply never falls back to a robotic TTS while claiming to be that voice: if no clone engine
is installed, ARC says **"reply voice: the system voice"** in words.

Both are in the app, both are per machine, and the app now *says* which reply voice is
active — one line, right under the voice section:

```
Reply voice: your own recording, spoken by indicf5 (9.2 s reference).
Reply voice: the system voice — no reply voice added yet (Settings → Voice → Voices…).
Reply voice: the system voice — a clip is added, but no engine is installed yet
             (Settings → Voice → Get the reply-voice engine…).
```

### Adding a reply voice (any voice)

1. **Settings → Voice → Voices…**
2. In *2 · The voice ARC answers in*: type a name, click **Add a voice…**, pick the
   recording (WAV/MP3/MP4), type the words it says, choose Tamil / Hindi / English.
3. It is graded with numbers (length, grade, SNR) and stored as its own file.
4. **Answer in this voice** — from now on every reply uses it. **Hear it** speaks a line.

Two clips of two different people can sit side by side and you can switch between them in
one click. Removing the one in use falls back to another, never to silence.

### The engine that makes it a person — one button

A cloned voice is not a setting, it is a model. **Settings → Voice → "Get the reply-voice
engine…"**, or the same button inside the voice library:

| engine | languages | size | one-off download |
|---|---|---|---|
| **IndicF5** | Tamil, Hindi | ~1.5 GB | tick, press Install, watch the lines scroll |
| **XTTS-v2** | English | ~1.9 GB | same |

- **Stop** works — and then the app says "stopped", never "installed".
- Nothing counts as ready until the **weights** are on disk, not just the package.
- A failure keeps the real error line on screen instead of "something went wrong".
- Downloaded once, kept on this computer. Nothing is installed globally.

**The installed `.exe` can do this too.** It cannot import a package that arrives later
(and torch inside the installer would add ~2 GB), so the app borrows the Python already on
the computer, builds a **private folder** of its own (`ArcDesk\engine_env`), installs the
engine there, and speaks by handing one sentence to `tools/clone_speak.py` with that
interpreter. One button from your side; nothing on PATH, nothing global. If the computer
has no Python at all, the dialog says that in one sentence and points at python.org — it
does not pretend, and the free piper voice keeps working meanwhile.

**Speed, said plainly:** cloning on a CPU takes seconds per sentence. That is the model,
not a bug. On a GPU it is instant. ARC keeps answering in the free voice until the engine
is ready, and says which voice it is using.

### Answers in my voice (the clone)

1. **Settings → Voice → Use my voice for replies…**
2. *Choose a recording…* — a WAV/MP3/MP4 of yourself, ideally **10–12 s**, one voice,
   no music, quiet room. Tamil or Hindi typed in the *transcript* box (IndicF5 needs the
   words); pick the language, or leave *Auto* and it reads the script.
3. **Add a voice…** — it prints the length, a grade and a measured SNR, and tells you
   honestly when the clip is too short (`short` = clean but under 8 s).
4. **Answer in this voice** — every reply uses it from now on. **Hear it** speaks one line.
5. Two clips of two different people can sit side by side; switching is one click, and
   removing the one in use falls back to another — never to silence.

The one thing the app cannot invent: a cloned voice needs a neural engine installed.
**Settings → Voice → "Get the reply-voice engine…"** — IndicF5 (~1.5 GB) for
**Tamil/Hindi**, XTTS (~1.9 GB) for **English**, installed from inside the app with live
output and a Stop button (see §1c). Without it ARC says "reply voice: the system voice"
instead of quietly answering in a stranger's voice. Piper (the offline fallback) is a *real* Tamil voice but
**not yours**, and the status line names it as such.

## 1d. If "hey jarvis" does nothing — the ears

Four separate things, and the app now shows which one is missing instead of a grey
sentence: **Settings → Voice → "Get the ears ready (mic + wake word)…"** (also on the
setup card, which only offers it when the machine really cannot listen).

```
  ✔  microphone library            — sounddevice
  ✔  wake-word engine              — vosk
  ✗  speech model (40 MB)          — vosk-model-small-en-us-0.15
  ✗  speaker model — voice lock    — speaker_embedding.onnx
```

One button downloads the two models (70 MB) with the lines visible, **Stop** works, and
afterwards it **re-checks** — it never says "listening" because a download finished. If
the wake engine itself is missing from a compiled build, the dialog says so in one
sentence instead of spinning: a compiled `.exe` cannot add a Python package after the fact.

## 2. Only your voice wakes it, on this computer

### When, and where — the short answer

**Do it once, right after installing, in the app: Settings → Voice → "Teach ARC my
voice…"**. Three takes of four seconds each, in a quiet room, alone. No terminal, no
files to find. The card shows a live level bar so a dead microphone is obvious in the
first second rather than after a silent failure, and it counts the takes for you.

Then tick **"Only my voice may command ARC on this computer"** and press Done. That is
the whole submission. To undo it, untick the same box — the lock is per machine, so a
second laptop enrols the person who uses *that* laptop, never a copy of your biometrics.

If the microphone is unavailable, the same card has **"Use a WAV file…"**. If the
speaker model is missing it says so and offers to download it (30 MB) instead of
pretending to be ready.

**Prove it actually works** rather than trusting the screen:

```bat
python tools\voice_setup.py selftest --against other.wav
```

That imports a reference, enrols three takes, then scores a take it has never seen (your
voice — must pass) and another person's recording (must fail). Measured here with the real
`campplus` model on real audio: same voice **0.70**, another voice **0.16**, threshold
**0.62**.

### The command-line version (same machinery, for scripting)

```bat
python tools\voice_setup.py lock-model
python tools\voice_setup.py lock-enroll me rec1.wav rec2.wav rec3.wav
python tools\voice_setup.py lock-test  rec4.wav
python tools\voice_setup.py selftest --against rec4.wav   :: import + enrol + prove
python tools\voice_setup.py lock-on
```

* **3 recordings, 3–8 seconds each**, same person, quiet room, normal speaking voice.
* The clips are reduced to a **fingerprint** (a unit vector). The audio is not kept.
* Enrolment measures how much your own clips agree and **raises its own threshold**
  from that: inconsistent clips make the lock stricter, never looser.
* Two people can be enrolled on one machine (you and your wife, say); the closest
  match wins and is named in the log.
* With **nobody** enrolled the lock stays **open** — a lock that shuts the owner out
  is a bug, not a feature.
* The daemon checks the **command audio** (not just the wake word), because that is
  when real work is about to happen:

```
VOICE · wake word detected
voice lock: me (0.81)
heard: open notepad
```

Rejected:

```
voice lock: rejected (score 0.41 < 0.62) — not acting on it
```

### What this is not

This is a **convenience filter, not a security control.** It keeps your family, the
television and a YouTube video from waking ARC. It does **not** stop a recording of
your voice on a phone — no system that runs on one microphone can. If it is off, is
broken, or has no model, the app says so and falls back to the plain wake word.

Turning it on without an engine is refused with the reason, and the app never claims
to be locked when it is not.

---

## 3. A second laptop

| What | How |
|---|---|
| **This laptop** stays yours | `%APPDATA%\ArcDesk\voiceid\profiles.json` holds your fingerprint |
| **Laptop B** is someone else's | it has its own (empty) folder → run `lock-enroll` there with *their* recordings |
| you *want* the same voice on both | there is no command for that on purpose; copy the profiles.json yourself if you really mean it |
| the cloned voice on both | copy `%APPDATA%\ArcDesk\voice\` — or just run `import` again on B |

---

## 4. What was actually run here

```
python tests\test_clone.py        ALL PASS   (routing, trimming, stitching, refusal, fallback)
python tests\test_voiceid.py      ALL PASS   (enrol, verify, thresholds, per-machine profiles)
python tools\voice_setup.py status           no clone engine installed — and it says so
python tools\voice_setup.py import <clip>     stitched 5.9 s · 24 kHz mono
```

The 1.5 GB models were **not** downloaded and could not be run in the sandbox that
built this. `status` reports `no — missing the IndicF5 weights and the 'transformers'
package` instead of claiming a cloned voice you would not hear.
