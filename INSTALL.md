# Installing Arc Desk on your laptop

The end state you described:

> **"HEY JARVIS"** → the ARC world opens, fullscreen.
> **"BYE JARVIS"** → it closes, Windows is normal again.
> Everything magical lives *inside* the app.

This is now a real, installable Windows application. Here is how to build and install it.

---

## 1. The one-click way (what you actually want)

On a Windows machine, once:

```bat
packaging\build_all.bat
```

That single command downloads the portable runtimes (ffmpeg + node, **on this machine
only**), builds both executables, and compresses everything into:

```
dist\ArcDeskSetup.exe        <- this is the file you carry around
```

**The step-by-step for that path is `SETUP_GITHUB.md`** (empty repo → drag the folder in →
green tick → download the artifact). If you have git, `push_to_github.bat <repo-url>` does
the same in one command and prints the Actions link.

**No Windows PC, and no repo yet?** `arcdesk-src.zip` in the workspace root is the whole
source (17.6 MB). Unzip it into a new GitHub repo — the `.github/workflows/` folder comes
with it — then *Actions → "build windows installer" → Run workflow*.

**No Windows PC? Build it on GitHub's machine.** Push this repo, then
*Actions → "build windows installer" → Run workflow*; the `ArcDeskSetup` artifact it
uploads is the same `ArcDeskSetup.exe`. Everything (Python, the voice libraries,
ffmpeg/node, PyInstaller, Inno Setup) is installed on the runner, never on your laptop.

**Then the person installing does exactly one thing: double-click it.** No Python, no
ffmpeg, no node, no PATH editing, no terminal. The last screen says *"Arc Desk is
installed successfully."*

What the installer does, in full:

| | |
|---|---|
| Installs to | `%LOCALAPPDATA%\Programs\ArcDesk` — **per-user, no admin prompt** |
| Carries | the app, its own Python (frozen inside `ArcDesk.exe`), ffmpeg + ffprobe, optional Node |
| Creates | Start Menu entry, optional desktop shortcut, uninstaller |
| Asks | *"How should it open?"* — desktop icon, or start with Windows and listen for "hey jarvis" (both pre-ticked, both undoable later in Settings → Voice) |
| Optional tick | the two speech models (70 MB: Vosk 40 + speaker 30) — checked by default, downloaded visibly, re-offerable in Settings → Voice |
| Never does | services, scheduled tasks, drivers, firewall rules, PATH edits, registry writes outside that one Run value |
| Uninstall | stops both processes, removes the startup value, and **asks** before deleting your vault |

### Manual build (if you want the pieces separately)

Requirements: Python 3.10+, and the repo on your machine.

```bat
python tools\packaging.py     :: what would break the build?
packaging\build.bat           :: the two exes only
packaging\make_installer.bat  :: wrap an existing dist\ into a Setup
```

Produces:

```
dist\ArcDesk\
    ArcDesk.exe        the ARC world   (window, HUD, magic mode, charms)
    ArcDeskVoice.exe   the ears        (wake word + microphone, separate process)
    _internal\...      Qt libraries and the generated pages
```

`packaging\build.bat` runs five steps and stops at the first problem: python version, required
packages, `tools\packaging.py` (spec/paths/installer/uninstall all checked), a clean of the
old work folder, then PyInstaller. It never installs anything and never writes outside
`dist\` and `build\work\`.

Two executables on purpose: the UI must never share a process with a microphone and a
speech model — that separation is what keeps the app at ~82 MB (`PERFORMANCE.md`).

### A second laptop

Copy `dist\ArcDeskSetup.exe`, install it there, then carry the *data*:

```bat
python tools\move.py pack D:\arcdesk-carry.zip     :: here
python tools\move.py unpack D:\arcdesk-carry.zip   :: there
```

Models are downloaded on the new machine, and the voice lock is enrolled fresh with the
voice of whoever uses that machine. Full detail: `MOVE.md`.

**The installer asks how it should open** — desktop icon, or start with Windows and listen
for "hey jarvis". Both are pre-ticked because listening is what makes the wake word work;
untick either, and the same choice is waiting later in Settings → Voice → "How ARC opens".

**The installer also offers the models**: one checkbox at the end,
*"Download the speech models now (70 MB)"* — 40 MB Vosk (commands) + 30 MB speaker model
(voice lock). It is checked by default and runs visibly. If it fails (offline, proxy), the
app is still installed and Settings → Voice offers the same download again. Skipping it
means "hey jarvis" will not work until it is done, and the status line says exactly that
rather than failing silently.

Equivalently, from a prompt in the installed folder:

```bat
ArcDesk.exe --download-voice-model
```

### Optional: your own voice (cloning) and voice lock

```bat
install_clone.bat          :: shows every download and its size, asks before the big ones
```

| Piece | Size | What for |
|---|---|---|
| sherpa-onnx + speaker model | ~30 MB | voice lock: only the enrolled voice may command it |
| piper | ~50 MB with a voice | free fallback voice, fast, any language |
| IndicF5 | ~1.5 GB | clone your voice in **Tamil / Indic** (GPU recommended) |
| XTTS-v2 | ~1.9 GB | clone your voice in **English** (personal use licence) |

Then: `python tools\voice_setup.py import "clip.mp4"` and
`python tools\voice_setup.py lock-enroll me r1.wav r2.wav r3.wav`. Full detail and
the honest limits are in `VOICE.md`.

### What the build actually measured

Not estimates — the numbers from a real run of `packaging/build_all.sh`, which uses the
same spec, the same pre-flight and the same two executables as the `.bat`:

| | |
|---|---|
| PyInstaller, both executables | **51 s** |
| Whole build, one command, cold | **1 min 58 s** |
| Packaged folder `dist/ArcDesk` | **298.5 MB** (Qt 100, sherpa-onnx 32, Python 28, numpy 27, Pillow 14, lxml 9.4) |
| Same folder, LZMA2 compressed | **86.4 MB — 29 %** |
| Frozen `ArcDesk --version` / `--doctor` / `--screenshot` | run, and render the real UI |

The `.sh` does **not** produce the Windows installer — PyInstaller cannot cross-compile.
What it does prove is everything the `.spec` gets wrong when it is wrong: the data files,
the hidden imports, the three generated HTML pages, `tools/doctor.py`, and whether both
frozen entry points actually start.

## 2. Install it (pick one)

### A. Proper installer (recommended)

```bat
packaging\make_installer.bat
```

Needs [Inno Setup 6](https://jrsoftware.org/isdl.php) — a **free** tool
(`winget install JRSoftware.InnoSetup`). It produces `dist\ArcDeskSetup.exe`, which:

- installs into `%LOCALAPPDATA%\Programs\ArcDesk` (no admin prompt)
- creates Start Menu + optional desktop shortcut
- optional "start with Windows" entry that launches **silently** (`--shadow`)
- registers a proper uninstaller that stops both processes first, removes the autostart
  value, and **asks** before deleting your notes and journal

### B. No installer

```bat
packaging\build.bat
install_shortcut.bat
```

Creates the same shortcuts via PowerShell. Same result, less polish, no extra download.

## 3. First run — three clicks

1. Launch **Arc Desk** (Start Menu or desktop).
2. `⋯ → Settings… → Voice` → tick **Listen for the wake word**, check the phrase says
   `hey jarvis`, click **Save**.
3. If the status line says the model is missing: run `install_voice.bat` once
   (vosk + sounddevice + a 40 MB model, all free).

Test without a microphone first: `⋯ → Test wake word (no mic)`.

## 4. What "open" and "close" mean

Both are real, and both are a setting:

| `Settings → System → On "BYE JARVIS"` | What happens | Best for |
|---|---|---|
| **Hide to background** (default) | ARC disappears, wallpaper restored, the process stays in the background with the mic armed → next "Hey JARVIS" is **instant** | normal use |
| **Close the app** | ARC disappears *and the process exits*. A small launcher daemon stays behind, listens for the wake word, and starts the app again | "I want it truly closed" |

Honest note about the second option: after the app exits, the launcher daemon takes 3–6 seconds
to load the speech model before it can hear you again. That is the price of a real process exit.
The default (`hide`) has no such gap, which is why it is the default.

```
"HEY JARVIS"                       "BYE JARVIS"
     ↓                                  ↓
launcher/app hears it              wallpaper restored
     ↓                                  ↓
cinematic (1.9 s)                  app hidden  ── or ──  app exits,
     ↓                                                    launcher armed
fullscreen ARC world
+ wallpaper swapped
```

## 5. What the ARC world contains

- Fullscreen reactor with the clock
- Six app tiles + one command line (typed or spoken)
- Gravity charms floating over your desktop when you leave magic mode
- The console (`Ctrl+J`) with 88 tools
- Optional for `explain` on the screen (not for pasted text): Tesseract —
  `winget install UB-Mannheim.TesseractOCR`. Without it, ARC says so and reads
  whatever you paste instead
- Everything from the earlier phases — all inside the app, nothing added to Windows

## 5b. If something does not work

```bat
check.bat                  :: tests + doctor + Windows check + stack scan
python run.py --doctor     :: just the install check
```

That is the first thing to run on a new machine, and the first thing to paste into a message if
you want help. It checks, in order: Python 3.10+, the Qt toolkit, whether the settings folder is
writable, whether `settings.json` is valid, whether the brain is free and allowed, whether any
local engine is running, whether the microphone library and wake engine exist, whether the
single-instance lock is free, whether this is a source or packaged build, that no
wallpaper/taskbar/explorer code exists, disk space, and recent errors in the log.

Two results need no action: `[info]` means "not installed, and that is fine", `[warn]` means
"usable but a feature will stay quiet".

The log is at `%APPDATA%\ArcDesk\logs\arcdesk.log` — **Settings → System → Open log** shows
it. It is the only way to see a crash in the packaged build, because `console=False` means there
is nowhere else for the traceback to go.

## 7. Optional extras: eyes, email, calendar

None of these are needed to start ARC. Each is switched on by installing one thing or
by filling in one block in `%APPDATA%\ArcDesk\settings.json`.

### Eyes (OCR) — lets ARC read your screen and click by label

```bat
winget install UB-Mannheim.TesseractOCR
```

Then "what does this error say" and "click Save file" work. `tests/test_vision.py`
proves the pipeline on a synthetic screenshot: full-page OCR, a second pass that
detects UI rectangles (a white label on a blue button is invisible to a page-wide
pass), and a click point verified to land inside the button.

Clicking itself needs nothing extra on Windows (PowerShell). On Linux install
`xdotool` (and `pyatspi` if you want the accessibility tree instead of pixels).

### Email — your own SMTP account, password never stored

```json
"comms": {
  "email": {
    "host": "smtp.gmail.com",
    "port": 587,
    "user": "you@gmail.com",
    "from": "you@gmail.com",
    "password_env": "ARCDESK_SMTP_PASSWORD",
    "use_tls": true
  }
}
```

```bat
setx ARCDESK_SMTP_PASSWORD "your-app-password"
```

Gmail needs an **app password** (2-Step Verification on). The password lives in the
environment, not in the settings file, so it cannot leak through a backup or a
screenshot of your config. Without it, `email_send` says exactly what is missing and
`email_draft` still works — that one just opens your mail app.

### Calendar — files, not an account

`calendar` writes `.ics` files into `~/Calendar` (configurable) and reads them back,
plus any read-only subscription URLs you add under `comms.calendar.ics_urls`. No
OAuth, no Google project, no token to expire. `tests/test_comms.py` round-trips a
real event, including titles with commas and semicolons.

### WhatsApp

`whatsapp_send` opens `wa.me` with the text pre-filled. You press send. That is
deliberate — automating a personal messenger with stored sessions is how accounts get
banned, and it is not something an assistant should do behind your back.


## 8. Uninstall

Start Menu → **Uninstall Arc Desk**, or `uninstall.bat`. It stops `ArcDesk.exe` and
`ArcDeskVoice.exe`, removes the startup entry, and deletes `%APPDATA%\ArcDesk`.
Windows itself is left exactly as it was.

## 9. Two honest limits of this build

1. **`ArcDesk.exe` must be built on Windows.** PyInstaller cannot cross-compile, so the
   `.exe` cannot be produced in the Linux sandbox where the code was written and tested.
   The logic is verified (`tests/test_app_lifecycle.py`), the binaries need your machine.
2. **The packaged voice backend needs vosk + sounddevice installed** into the same Python
   that PyInstaller used, *before* building, so they get bundled. If you skip that,
   `ArcDeskVoice.exe` will start and then exit with "no speech engine" — the app still runs,
   Lite mode and typing still work.
