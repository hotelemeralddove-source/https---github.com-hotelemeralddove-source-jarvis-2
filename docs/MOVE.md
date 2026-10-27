# Another laptop — yes, and with the other person's voice

Two questions, answered in one page:

1. *"can I install this on another laptop?"* — **yes**, one installer plus one data
   package.
2. *"can it work with a different voice there?"* — **yes**, and that is the one thing
   that must be different, not copied.

---

## 1. The program (built once, on a Windows machine)

```bat
packaging\build_all.bat          :: on ANY Windows machine with Python 3.10+
-> dist\ArcDeskSetup.exe        :: carry this file
```

On laptop B: double-click it. No admin prompt, no Python/ffmpeg/Node installation, no
PATH editing, last screen *"Arc Desk is installed successfully."*

**The honest limit:** PyInstaller does not cross-compile. This project is developed on
Linux, so the `.exe` is produced on a Windows machine — `tools\packaging.py` reports
that step as `UNVERIFIED` rather than pretending it happened. Nothing else about the
move depends on it.

## 2. Your data — one command each side

```bat
:: laptop A
python tools\move.py pack D:\arcdesk-carry        :: a folder
python tools\move.py pack D:\arcdesk-carry.zip    :: or one file, easier to send

:: laptop B, after installing
python tools\move.py unpack D:\arcdesk-carry.zip
```

| travels | why |
|---|---|
| `vault/` | your projects, notes, progress — the actual work |
| `voice/` | the clone reference clip and its transcript |
| `settings.json` | preferences, **API keys stripped** (`--with-keys` to keep them) |
| `profile.json`, reminders, focus sessions, the magic journal | what it knows about you |

| stays behind | why |
|---|---|
| `voiceid/` | the voice lock belongs to a person *and* a machine — see §3 |
| `models/` | 1.5–2 GB of weights; downloaded by the installer on B, never copied |
| `logs/`, caches, the file index | this machine's noise |
| `art/`, `photos/`, `generated/` | can be gigabytes — `--with-media` if you want them |

Unpacking over an existing vault is **refused** unless you say `--merge` (keep both) or
`--force` (replace). A move can never silently delete someone's project.

## 2b. First run on the new laptop asks one question

After installing there, the setup card asks how it should open: **desktop icon** or
**voice**. On the second machine the sensible answer is usually *icon* while you are still
setting it up, then switch to *voice* from Settings → Voice when it is where you want it.
Changing your mind is one click in either place, and it takes effect immediately.

Then teach it the voice of whoever uses that laptop (not yours, if it is someone else's):

```bat
:: Settings -> Voice -> "Teach ARC my voice..."  -- three takes, in the app
python tools\voice_setup.py selftest --against their-other-voice.wav   :: prove it
```

Nothing about the lock travels in the zip, by design.

## 3. A different voice on the other laptop

This already works, by design:

| | laptop A | laptop B |
|---|---|---|
| who may wake it | whoever is enrolled **in A's** voice folder | whoever you enroll **in B** |
| how | `voice_setup.py lock-enroll me r1.wav r2.wav r3.wav` | `voice_setup.py lock-enroll <name> r1.wav r2.wav r3.wav` |
| shared? | no — the package excludes `voiceid/` on purpose | starts empty, so the lock stays open until B enrols |
| the clone voice | A's reference clip travels with the package | re-import a clip of *B's* person if the speaker changes |

So: **install on B, unpack the data, re-download the models, enrol B's voice.** Four
commands, and neither machine can lock the other out.

## 4. Models — downloaded, not carried

| model | size | command on laptop B |
|---|---|---|
| Vosk speech model (for commands) | 40 MB | `install_voice.bat` |
| speaker model (voice lock) | 30 MB | `python tools\voice_setup.py lock-model` |
| piper voices | ~50 MB | `install_clone.bat` |
| IndicF5 (Tamil + Hindi cloning) | ~1.5 GB | `install_clone.bat` |
| XTTS (English cloning) | ~1.9 GB | `install_clone.bat` |
| Ollama model (optional brain) | 1–4 GB | `setup_free_ai.bat` |

Copying them is possible but pointless: paths, GPU drivers and CPU threads differ, and
a wrong-arch file fails in a way that is hard to explain. Downloading is 5 minutes.

## 5. A USB stick instead of a second laptop

```bat
set ARCDESK_HOME=E:\ArcDesk          :: everything — settings, vault, voice — on the stick
python run.py
```

or set `vault.portable = true` so only the vault follows the stick. This is the same
data as the package above, just live instead of zipped.

## 6. What was run

```
python tests\test_move.py    ALL PASS  (pack/unpack, key stripping, merge, force, per-machine voice)
python tools\move.py check   lists what travels, what is left behind, and why
```

The one thing never claimed: a working `ArcDeskSetup.exe` built from here. That is a
Windows step, and it says so.
