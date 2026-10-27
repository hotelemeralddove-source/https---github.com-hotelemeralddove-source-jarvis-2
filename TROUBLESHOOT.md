# When it will not start

Every row below is a real dialog, with the exact cause and the exact clicks. If your
dialog is not here, run **`ArcDeskDiag.bat`** (double-click, nothing to install) and send
me `ArcDeskDiag.txt` — it answers the questions a screenshot cannot.

---

## The one you sent

> **AppInstallerPythonRedirector.exe — Application Error**
> The application was unable to start correctly (0xc0000142). Click OK to close.

**What the title means.** `AppInstallerPythonRedirector.exe` is not part of Arc Desk.
It is the **Microsoft Store's Python alias** — the stub Windows runs when something asks
for `python.exe` and the only Python is the Store package (or a leftover of it). Its
presence in the title is proof: *something on this PC launched Python, and that Python is
the Store alias.*

**What `0xc0000142` means.** `STATUS_DLL_INIT_FAILED` — a DLL refused to initialise. For
us there are exactly three ways to get it:

| # | Cause | How to tell | Fix |
|---|---|---|---|
| 1 | **The setup/app was built with the Store Python.** PyInstaller copies DLLs from a Store package folder with restricted ACLs; the frozen app cannot load them. The build "succeeds", the exe never opens. | `where python` prints a path containing **WindowsApps** | Turn the alias off, install Python from **python.org**, rebuild. `packaging\build_all.bat` now refuses to build with the Store alias |
| 2 | **The VC++ runtime is missing** on this PC (Qt needs `vcruntime140.dll`, `msvcp140.dll`). | `C:\Windows\System32\vcruntime140.dll` does not exist | Install **Microsoft Visual C++ Redistributable (x64)**, or use a build that ships the DLLs beside the exe (the spec now bundles them) |
| 3 | **The download is truncated or blocked.** | The `.exe` is much smaller than 53 MB, or `ArcDeskSetup.exe.zone.identifier` exists | Delete it, download again; or right-click the file → **Properties → Unblock → OK**. `ArcDeskDiag.bat` does this for you |

**The order I would try them, for you right now:**

1. **Use it today, no installer.** Right-click `ArcDesk-portable.zip` → **Extract All** →
   open the folder → double-click **`ArcDesk.exe`**. Nothing is installed, nothing is
   registered, and this needs no Python on your PC at all.
2. **Run **ArcDeskDiag.bat**.** It says in one page whether the file is blocked, whether
   your Python is the Store alias, and whether the runtime is there. Send me the report.
3. **Rebuild only if you want the installer.** With a python.org interpreter:
   `packaging\build_all.bat` — the new step 0 stops with a one-line fix if anything is
   wrong, instead of producing a 53 MB file that cannot open.

---

## "The shortcut is on the desktop but nothing happens"

That is the windowless bug from the other side: the app died in its first second, and a
program with no console has nothing to say about it.

Two ways to see it, in this order:

| Do this | Why |
|---|---|
| Double-click **`ArcDeskStart.bat`** | it keeps a black window open while the app starts, so the error stays on screen instead of vanishing |
| Double-click **`ArcDeskRepair.bat`** | it finds every copy on the PC, starts each one, waits 8 seconds, and tells you which one works. If one works it rebuilds your desktop shortcut to point at it. If none work it names the reason |

The three reasons, and how the repair file tells them apart:

| Cause | The check | Fix |
|---|---|---|
| Built with the **Microsoft Store Python** | `where python` shows a path containing `WindowsApps` | turn the alias off (Settings → Apps → App execution aliases), install Python from python.org, rebuild |
| The **VC++ runtime is missing** | `C:\Windows\System32\vcruntime140.dll` not found | install **Microsoft Visual C++ Redistributable (x64)** |
| The **folder is incomplete** — only `ArcDesk.exe` was copied, not `_internal` | no `_internal` folder beside the exe | copy the whole folder, or reinstall. A packaged app is the exe **plus** that folder |

### And the icon

The shortcut in your picture shows a **yellow-and-blue box** — that is PyInstaller's own
icon, not Arc Desk's. It means the build could not find `shots/arc_icon.ico`, so the exe
carried the fallback. It is cosmetic, but it is also a signal: the build machine was
missing something, and the same run is where the missing DLLs come from.

`tools/preflight_win.py` now **fails the build** when the icon is missing, and
`install_shortcut.bat` writes a shortcut with an explicit `IconLocation`,
`WorkingDirectory` and a target that actually runs — never a shortcut to a `.py` or `.pyw`,
because those get the Python icon and fail silently by design.

---

## Other dialogs, same treatment

| What you see | Cause | Fix |
|---|---|---|
| **"This app can't run on your PC"** | 32-bit build on 64-bit Windows, or the file is a half-download | Download again. `python tools\preflight_win.py` refuses a 32-bit interpreter |
| **"Windows protected your PC"** (blue box) | SmartScreen, because the exe is not code-signed | **More info → Run anyway**. Signing needs a paid certificate — this app ships unsigned on purpose rather than hiding that |
| **"MSVCP140.dll was not found"** | The VC++ runtime, exactly as row 2 above | Install the x64 redistributable, or use a build that bundles it |
| It opens and **closes instantly, no window** | A windowless crash. Before this fix there was no trace anywhere at all | `%APPDATA%\ArcDesk\logs\arcdesk.log` — the app now points its own stdout/stderr there and keeps the traceback |
| It runs but **"hey jarvis" does nothing** | The ears (microphone, wake word) or the 70 MB speech models are missing | **Settings → Voice → "Get the ears ready…"** — it ticks or crosses the four things and downloads what it can |
| It answers **in the system voice, not yours** | No clone engine installed | **Settings → Voice → "Get the reply-voice engine…"** (Tamil/Hindi: IndicF5, English: XTTS) |
| **Several black command prompts** appear while it works | Fixed: every child process is now spawned with `CREATE_NO_WINDOW` (`arcdesk/quiet.py`) | Make sure you are running a build from fix pack 16 or later |
| The **uninstaller asks about your vault** | On purpose. Your notes and files are yours | Answer **No** to keep them; they live in `%APPDATA%\ArcDesk\vault` |

---

## Two files worth knowing

```
%APPDATA%\ArcDesk\logs\arcdesk.log      everything the app would have printed
%APPDATA%\ArcDesk\settings.json         all settings; safe to copy to another PC
```

`python tools\move.py pack D:\carry.zip` puts your settings, vault and clone clip into
one file (keys stripped) if you are changing machines.

---

## For the person building it

```bat
python tools\preflight_win.py     :: judge the machine before PyInstaller does anything
packaging\build_all.bat           :: runs the same check as step 0, then builds
```

`preflight_win.py` fails the build — with the fix printed — when:

* `python` is the Store alias (exit 1, before PyInstaller is even called),
* the interpreter is 32-bit or older than 3.9,
* PySide6 or PyInstaller is missing,
* there is not enough disk for a ~1.2 GB build folder,
* the repo sits inside a OneDrive folder (OneDrive locks files mid-build),
* the path is longer than 110 characters (Windows gives up at 260).

It warns, but does not fail, when there is no venv, no Inno Setup (the app still builds;
only `ArcDeskSetup.exe` needs it) and no icon.

## The desktop icon is a yellow Python, not Arc Desk

That picture — a yellow snake over a white page on a blue floppy — is PyInstaller's
**default** icon. It means the `.exe` you are running was produced without
`icon=shots/arc_icon.ico`, i.e. not by `packaging/arcdesk.spec` (the old fallback build
did exactly this), or by a build where the icon file was not found.

**There was a second cause, found after the first was fixed**: the `.ico` file's small
frames were PNG-compressed. That is legal and Windows renders it at 256x256, but the sizes
a desktop shortcut actually uses (16/32/48) are where Explorer gives up and falls back to
the *file type's* icon — the python. `tools/make_icon.py` now writes BMP/DIB frames for
every size below 256 and PNG only for 256, the layout every Windows icon tool produces.
`tests/test_windows_build.py` asserts that layout, so it cannot silently come back.

How to tell in ten seconds: open the program folder and look for `ArcDeskVoice.exe` and
a folder called `_internal`. The fallback build has neither. Arc Desk's real build has
both, plus the sparkle icon.

Two things can look identical on screen, so check both:

1. **The exe is old** — reinstall from the newest green run's `ArcDesk-portable.zip`.
   Delete the old program folder *and* the old desktop shortcut first, so a stale
   picture cannot survive (see below).
2. **Windows is showing a cached icon** — Explorer remembers icons *per file path*.
   Copy the whole folder somewhere else and rename it (`ArcDesk2`); if the copy shows
   the sparkle icon, the exe was always fine and only the cache was wrong. To clear it
   without a copy: rename the shortcut, or run `ie4uinit.exe -show`.

The build now refuses to publish an exe whose icon is not Arc Desk's — the workflow
asks `python tools\preflight_win.py --icon-check dist\ArcDesk\ArcDesk.exe
shots\arc_icon.ico`, which compares the icon's bytes with the bytes inside the exe.

## It installs, but nothing happens (no window, no card, nothing)

This was a real bug, fixed in this build, and it is worth knowing what it was.

The app could be told to "start hidden" — stealth mode, no window, no card, only a tray
icon. Two things were wrong together:

1. that hidden start was the **default**, so a fresh install was already in stealth; and
2. `--shadow` (the flag the boot entry passes) was **written into settings.json**, so one
   boot with Windows left every later double-click starting a process that showed nothing.

Now: a double-click always shows the window (the Windows shortcuts pass `--show`), the
boot entry still passes `--shadow` and still starts silent, `--shadow` never becomes a
saved preference, and the app writes its decision to the log so a silence can be read:

    BOOT · the window is shown
    BOOT · handles: tray=yes, hotkeys=yes, stealth=off

Settings files from an older build that say `"enabled": true` without `user_choice` are
corrected once (the same migration pattern the charms use). If you *did* tick "start
hidden" in Settings, that is a real choice and it is kept.

If it is still silent after this version: run `ArcDeskDiag.bat` and send the report —
it now carries the last 60 log lines, `settings.json`'s key values, and the size of the
installed exe. A report with no log at all means the exe never reached its own start-up
code, which is a different fault (and a much more specific one to send back).

## It takes too much disk space

What is actually big, in order: Qt (about 200 MB installed — the window library), the two
speech engines (about 60 MB), numpy (about 60 MB), Python itself (about 45 MB). None of
that is padding; it is what makes a window, an ear and a calculation work without Python
installed on the machine.

What you do not have to carry:

* **ffmpeg** — 195 MB installed. Only needed for video/audio waveforms and reels. The
  installer's default type is now **"Arc Desk only"**; pick "full" (or tick the box) only
  if you want it. Re-running the installer adds it later without touching your vault.
* **Node runtime** — 85 MB. Only for MCP tool servers over npx.
* **The old copy.** Two installs of Arc Desk means two copies of all of the above. If
  `Task Manager` ever showed two `ArcDesk.exe` entries, that is 200 MB+ of duplicates.
  `ReinstallClean.bat` removes the old one and never touches `%APPDATA%\ArcDesk`.
* **The downloaded files.** `ArcDesk-portable.zip` and `ArcDeskSetup.exe` each contain a
  whole copy (about 90 MB and 50 MB). Delete them once the app runs.

The build now prints a size breakdown (the 15 biggest files) on every run, and switches
the portable zip to 7-Zip maximum compression. Size is watched, not guessed — but it never
blocks a working build: a jump prints a warning and ships anyway.

## It talks too fast / it sounds like a machine / it lags

**Voice.** Settings → Voice now has three controls that were previously a number nobody
could find: *How fast it speaks* (default **-2**, unhurried; it used to be **+1**),
*Accent* (en-IN by default — JARVIS picks the best Indian-English voice Windows has
installed, and says which one, or says none matches instead of faking it), and *Pause
between sentences* (default **180 ms**; 0 ms reads like a machine reciting a list). The
engine is now given **SSML** with a stated rate and a break between sentences, instead of
one long string with a guessed speed. "Hear it" speaks a test line at exactly these
settings — the only honest test.

**Magic mode.** The screen shows the work, not only the hologram: a panel on the right
lists the request, the step running right now with its elapsed seconds, and the steps
already finished (`✓ tool · list_downloads · 1.2 s`). Everything in it comes from the
activity record, so it cannot display work that did not happen.

**Lag.** Three measured fixes:
* the full-screen hologram now adapts — when frames cost more than the budget it renders
  at 75% then 60% resolution and repaints every other frame (measured here: 19 ms → 9.6 ms
  per frame at 1920×1080), and returns to full quality when the machine catches up;
* `vision` (numpy + Pillow) and the Windows accessibility layer load on first use instead
  of at startup, and `smtplib` is imported only when mail is sent — startup imports
  dropped from 367 ms to 232 ms in this sandbox;
* nothing repaints while the window is hidden (this was already true and is still tested).

## "Python was not found... Microsoft Store" when double-clicking install.bat

That message is Windows' **App execution alias** answering for a Python that is not
installed. The alias is a 0-byte stub in `%LOCALAPPDATA%\Microsoft\WindowsApps`; it opens
the Store instead of running anything, and this app cannot build its environment with it.

The installers no longer stop and ask. `tools/pybootstrap.bat` is called by `install.bat`,
`install_voice.bat` and `install_clone.bat` and does what a person would:

1. looks for a real interpreter (`py -3`, the usual per-user install folders, `python`),
   **skipping anything under `WindowsApps`** and rejecting anything older than 3.10;
2. if none, offers one download — Python 3.12.8, 64-bit, from python.org — and tries
   `winget install Python.Python.3.12` first;
3. installs it **per-user** (`/quiet InstallAllUsers=0 PrependPath=1`), so there is no
   administrator password and nothing global changes;
4. looks again, then carries on with the environment it was asked to build.

If you would rather not, the two-click route is printed at that point with the exact URL,
and the one box to tick on its first screen is "Add python.exe to PATH".

**You probably do not need any of this.** If `ArcDesk.exe` exists — the installer or the
portable zip — the app needs no Python at all. `install.bat` is for running from source.

## Magic mode takes a second to appear, and its buttons open hidden windows

**Slow entry.** Measured: painting the magic wallpaper at 2560×1440 costs 168 ms, and it
was drawn *before* the screen was shown — first paint of the deck another 162 ms on top.
So half a second of nothing, and on a slower laptop the best part of a second. The screen
is now shown first (24–66 ms measured here) and the wallpaper is painted and applied
afterwards, off the GUI thread.

**"Notepad / Calculator open behind it."** They did: every tile called `open_app`, which
starts a separate Windows process. A fullscreen window that is always on top puts that
process *underneath* itself, so the click looked like it did nothing. Four tiles are now
owned by the app and open inside the deck:

* **NOTEPAD** — a real text pad with open/save
* **CALC** — a working calculator (mouse or keyboard; `__import__('os')` is refused)
* **FILES** — a folder browser that opens files with their default app
* **TASK MGR** — the top processes by CPU and memory, live

SETTINGS and BROWSER still belong to Windows (a UWP app cannot be embedded), so they are
launched and then brought to the front after a moment, so they appear *over* the deck
instead of behind it. Esc closes the panel before it closes magic mode.

## `ERROR: Could not open requirements file: requirements.txt`

Nothing is wrong with pip, and nothing is wrong with Python (the line above it says
`using: py -3`, so the bootstrap in fix29 did its job). **The folder is wrong.** A fix pack
is a handful of files that belong *inside* the project — unzip it on its own and there is
no `requirements.txt` beside `install.bat`.

Since fix31 the installers no longer trust where they were started from.
`tools/find_project.bat` looks for the one marker that cannot be faked — `run.py` sitting
next to `requirements.txt` — in this order:

1. the folder the `.bat` is in;
2. its parent (the usual case: fix pack unzipped *into* the project);
3. `Documents\GitHub\*` — where GitHub Desktop puts clones;
4. `Desktop\*`, `OneDrive\Desktop\*`, `Downloads\*`.

It then moves into that folder, prints it, and only then builds `.venv`. If it finds
nothing it says so in plain words, offers the three routes (already have `ArcDesk.exe` /
unzip the pack into the project / clone with GitHub Desktop) and **changes nothing** —
before fix31 it had already created a useless `.venv` in the wrong place by the time pip
complained.

The short version: **`ArcDesk.exe` needs none of this.** The `.bat` files are for running
from source, and they must sit next to `run.py`.

## "This is not the project folder" — and you have no project folder

That message is the fix for the `requirements.txt` error working: a fix pack is a handful
of files, not the app. If the answer to "do you have the project folder?" is *no*, nothing
in a fix pack can help — you need the source itself.

`JARVIS.bat` (in the project root) is the one file to hand to someone. It does the whole
job on a laptop that has never had Python:

1. `tools/find_project.bat` — confirm it is sitting in the project;
2. `tools/pybootstrap.bat` — find Python, or download and install the official one per-user;
3. build `.venv` and install `requirements.txt` (first run only, 2–4 minutes, needs
   internet);
4. start the app through `start_arcdesk.vbs` — no console, no window until "hey jarvis".

Run it again later and steps 2–3 are skipped: it starts in a couple of seconds.

## "ffmpeg is needed to read that file" when uploading a voice

That dialog was a dead end, and it is gone. The clip was fine — the app had no decoder for
it, and ffmpeg is a 100 MB program this installer deliberately does not carry (fix25 keeps
the download small), so telling a person to go install it was never the answer.

`arcdesk/audio.py` now reads the file with the smallest reader that can, **none of which is
ffmpeg**:

| reader | size | reads |
|---|---|---|
| `wave` (stdlib) | 0 | every WAV: 8/16/24/32-bit, mono or stereo |
| `soundfile` | ~2 MB wheel | WAV, FLAC, OGG, **OPUS** (WhatsApp voice notes), MP3 |
| `miniaudio` | ~1 MB | MP3, WAV, FLAC, Vorbis |
| `av` (PyAV) | ~30 MB | M4A/AAC, MP4, WEBM, MKV — everything else |
| `ffmpeg.exe` | — | only if the machine already has one |

If the file needs a reader that is not installed yet, **the app installs it and reads the
file straight after** — no dialog, no shopping list. The first upload on a fresh PC shows
"reading that recording… (the first one may install a small decoder)" while it happens.
`soundfile` is in `requirements.txt`, so normally nothing is downloaded at all.

Command voices are the same story: enrolling from an MP3 or an .opus used to fail deep
inside because the splitter only understood WAV. It now goes through the same reader.

## "Installing IndicF5" scrolls nothing and the bar does not move — is it stuck?

It was not stuck; the screen was lying. Two things were wrong:

* the progress bar was set to *indeterminate* with the comment "pip does not report
  percentages" — pip does, it draws them with a **carriage return** (`\r`) instead of a
  newline, and the reader in `engines._run` split on newlines only, so every update sat in
  a buffer until the download finished;
* nothing on the screen said **how many megabytes had arrived**, so a 1.5 GB download and
  a hung process looked identical.

Now:

```
   ━━━━━━━━━━━━━━━━━━━━━━━━ 45.2/779.9 MB 3.1 MB/s eta 0:04:00     (what pip prints)
   →  bar 6%  ·  45 of 780 MB · 3.1 MB/s · about 0:04:00 left · 2 min 41 s in
```

* `engines.read_progress()` understands pip's ascii bar and huggingface's tqdm bar
  (`812M/1.6G`), GiB included;
* the child is read in chunks and split on **both** `\r` and `\n`, so updates arrive live;
* `pip` is given `--progress-bar ascii`, which makes it draw a bar even into a pipe;
* the live line under the bar always shows the clock (updates every half second), so even
  a quiet stretch proves the app is working. When there is no percentage yet the bar reads
  "working" rather than a **0%** that looks like nothing is happening.

The 1.5 GB is mostly `torch`: expect 5–20 minutes on a normal connection, longer on a slow
one. "Stop" still stops it, and nothing is half-installed that matters.

## JARVIS.bat: a window flashes, Windows asks about a "script file", then nothing

That prompt came from `start_arcdesk.vbs`. A `.vbs` extracted from an internet download
carries the *mark of the web*, so Windows asks whether to open it — and if the answer is
Yes, the script starts `pythonw.exe` with `--shadow`, which by design shows no window. So
a successful start and a failed one looked identical: nothing on screen either way.

Three changes, all in `JARVIS.bat`:

1. **No more `.vbs`.** The app is started directly with
   `.venv\Scripts\pythonw.exe run.py --shadow` — no script host, no permission prompt.
2. **A log that outlives the window.** Every step is written to `jarvis-start-log.txt`
   next to the `.bat`, because a console that vanishes takes its error message with it.
3. **It checks what happened.** Six seconds after the start it looks for the process. If it
   is there, the window says so and lists the shortcuts; if it is not, it says the app
   started and died and points at the diagnosis route. A second double-click while JARVIS
   is already running says "already running" instead of pretending to start it.

**If a window only flashes: double-click `JARVIS-DIAGNOSE.bat`.** It runs the same app in
a visible console (no stealth, no `pythonw`), prints the Python version, then every line
the app produces, and waits for you to press a key. Its output goes to
`jarvis-diagnose-log.txt`. That file is the answer to "why did nothing happen".

Also worth knowing: if an earlier invisible instance is still running from the `.vbs`
attempt, a new start will correctly report "already running" and do nothing. Press
**Ctrl+Alt+Q** to quit it first.

## Which test covers which of these

Every bug above is held down by a test, so it cannot come back quietly:

| test | what it refuses to let happen again |
|---|---|
| `tests/test_installer_bootstrap.py` | a laptop with no Python getting a Microsoft Store stub and a dead end; a fix pack run in the wrong folder; `JARVIS.bat` starting through a `.vbs` or closing before it is read |
| `tests/test_audio.py` | "ffmpeg is needed to read that file" — WAV at four bit depths, mp3/ogg/flac, a broken file that must explain itself, and the whole upload path |
| `tests/test_ui_never_blocks.py` | the Settings hang: the engine probe never blocks the caller, clone.engines() asks the cache, the dialog builds in ~100 ms, find_spec instead of import |
| `tests/test_no_gui_probe.py` | the (Not Responding) freeze: a cold cache asked `cached_only` probes nothing, the status card's voice line never pays for a probe, the voice list is one background cost, and start-up pays it off-thread |
| `tests/test_one_place.py` | one folder: what counts as a copy, which one wins, --apply parks the rest, --undo restores, the tool refuses to move itself; plus the magic web's six named strands and hit targets |
| `tests/test_launcher_state.py` | the launcher's questions: lock socket not tasklist, only our python counts, stuck vs working, polite quit, the .bat wiring |
| `tests/test_install_safe.py` | installing piper/an engine used to close the app: find_spec instead of import, pip into the private folder, piper in a child process, faulthandler + session marker |
| `tests/test_engine_progress.py` | a 1.5 GB download that looks frozen: pip's ascii bar, huggingface's tqdm bar, carriage-return updates reaching the dialog |
| `tests/test_engine_found.py` | "terminal la all engines downloaded, but ipo kanom": packages found but weights missing reported as *not installed*, piper's engine and its voice files treated as one thing, and a background probe that answered after the screen had painted |
| `tests/test_engine_install_starts.py` | the dead Install button: a QThread treated as a dialog (`make_fit` → `AttributeError: layout`), the automatic button's `KeyError: 'id'`, a raise inside the worker that never came back, Stop against a silent child, and closing the window mid-download |
| `tests/test_crash_safety.py` | "yethavathu select pana application crash aagi close aaguthu": the engine never runs inside the window's process, a crash leaves crash-report.txt, and two crashes in a row start the app with the heavy visuals paused |
| `tests/test_engine_background.py` | the download that dies with the window: a detached helper, a JSON the screen can read, closing the dialog without losing 1.5 GB, Stop that keeps what arrived — and piper's voice download, which raised `TypeError` for every language |
| `tests/test_shortcut.py` | "every time jarvis.bat double click": the launch spec (`pythonw`, no console), the icon shipping from `assets/`, Desktop + Start Menu, and the create/repair/restore/off rules |
| `tests/test_engine_dialog_crash.py` | the crash report line by line: `done_after()` called with a button's bool, a running QThread destroyed with its dialog, a dialog taller than the work area, and an application-wide event filter on every event |
| `tests/test_every_option.py` | opens all twelve windows the app can show, one at a time, and reports which one (if any) raises — run with `--crashy` to give each its own process |
| `tests/test_safeopen.py` | a dialog that raises in its constructor, on screen, or on its worker thread — the app must stay, the reason must be written down, and the person must be told |
| `tests/test_voicematch.py` | the imported clip is really used: pitch measured, reply shifted onto it, length kept, short clips refused in words |
| `tests/test_qsafe.py` | the crash the person sent: close a download window while its thread runs — the thread must stop or stay referenced, and the app must keep standing |
| `tests/test_voice_playback.py` | pressing “play” on a reply voice: the button answers in milliseconds, the sentence is spoken off-thread, and the engine has a 3-minute ceiling |
| `tests/test_event_filter.py` | an event whose receiver is already deleted, a deleted object behind the focus, a fabricated dead event — the filter answers “not me” instead of chasing the pointer |
| `tests/test_perf.py` | the frame-rate governor, the lazy imports, and the magic-mode dock |
| `tests/test_magic.py` | entering magic mode fast, and the four tiles opening inside it |
| `tests/test_fit.py` | any dialog taller than the screen it is shown on |
| `tests/test_name.py` | the app calling itself ARC when it is JARVIS |
| `tests/test_update.py` | an update that refuses a good zip, copies over `.venv`, or needs PowerShell's type system |

## "IndicF5 engine downloading" and nothing ever comes down

Two reasons, and the second one is the one that matters:

1. **torch.** `pip install torch` on Windows is served a **CUDA build of about 2.5 GB**
   from PyPI. Most laptops have no NVIDIA GPU at all, so that whole download buys nothing —
   and on a home connection it is the difference between "a few minutes" and "never".
   The installer now takes torch from the **CPU-only index**
   (`https://download.pytorch.org/whl/cpu`, about 200 MB) and everything else from PyPI.
2. **The estimate was a guess.** It now uses the speed actually measured
   ("about 7 min left at this speed"), so a slow line is visible instead of suspicious.

### The easy route (take this one first)

| engine | download | needs | sounds |
|---|---|---|---|
| **Windows voice** | **nothing** — already on the PC | nothing | changed in fix28: slower, patient, with an accent |
| **Piper** | **~60 MB per language** | no GPU, no torch | neural, clearly human |
| IndicF5 | ~200 MB torch + ~1.3 GB weights | a GPU to feel instant | a clone of a voice you upload |
| XTTS-v2 | ~1.9 GB | CPU ok, slow | a clone, English only |

The engine dialog now lists the smallest first and labels Piper **"easiest"**. One click,
about a minute on a normal connection, and it speaks English and Hindi like a person — no
torch, no GPU, no 1.5 GB. Tamil *cloning* still needs IndicF5; Tamil without cloning is
already covered by Piper and the Windows voice.

If even 60 MB will not come down, the connection is the problem, and the Windows voice
needs no download at all: Settings → Voice → **Hear it** proves it in one click.

## `OSError: You are trying to access a gated repo … 401 Client Error` (IndicF5)

This is the real reason "IndicF5 keeps downloading and never finishes". Hugging Face was
refusing **every file**: `ai4bharat/IndicF5` is a **gated** model, so without a licence
acceptance the server answers 401 and the download can never complete. It is not the
connection, and waiting longer changes nothing.

Since fix35 the app checks the gate **before** it spends 200 MB of torch, and says so:

```
IndicF5 is a gated model: Hugging Face will not hand over a single file until its
licence is accepted once. Nothing was downloaded.
 1. open https://huggingface.co/ai4bharat/IndicF5 and click Agree (free account)
 2. make a read token at https://huggingface.co/settings/tokens
 3. paste it in this window and press Save, then Install again
 In a hurry? Piper is ~60 MB, needs no account…
```

The engine dialog now has a **Hugging Face token** field with a Save button. The token is
stored in this app's own settings (never printed, never in the repo) and is passed to pip
and to the model download as `HF_TOKEN`.

### Or skip it entirely

| want | engine | download | account needed |
|---|---|---|---|
| JARVIS to sound human, English | **Piper** | ~60 MB | no |
| JARVIS to sound human, Hindi | **Piper** | ~60 MB | no |
| a copy of *your* voice, Tamil or Hindi | IndicF5 | 200 MB + 1.3 GB | **yes, gated** |
| a copy of your voice, English | XTTS-v2 | 1.9 GB | no |
| speak at all, this minute | Windows voice | nothing | no |

`install_clone.bat` also asks "[Y,N]?" in a console; you never have to use it — the same
thing is one click in Settings → Voice → engine dialog.

## "It keeps repeating itself, does not listen patiently, gets confused"

Four separate faults, all found by reading the code rather than guessing:

1. **It stopped listening on a stopwatch.** `capture_command()` had one flat deadline
   (7 s) and ended the turn after **1.1 s** of quiet. A person thinking after "hey jarvis",
   or a Tamil sentence with a breath in it, was cut in half — then the half-sentence was
   answered, which reads as "it did not understand". Now: up to **12 s** for you to *start*
   talking (Settings → Wait for me to start), then the turn ends only after **1.8 s** of
   real silence, and it never cuts you off mid-sentence before **30 s**.

2. **Settings never reached the daemon.** The window started the voice daemon without
   passing `command_seconds` at all, so the number on the Settings page was decoration.
   The runner now passes `--command-seconds`, `--silence-seconds` and
   `--max-command-seconds`.

3. **It answered itself.** Half duplex relies on the mute arriving in time; a speaker tail
   or a Bluetooth headset's latency puts JARVIS's own sentence back into the ears a moment
   after the mute lifts, and it then "replies" to itself, out loud, forever. The window
   now sends `{"event": "said", "text": …}` before muting, and the daemon compares every
   transcript against it (`talk.said_myself`, 78 % similar = our own voice, ignored).
   A short command — "stop", "illa" — is never treated as echo.

4. **One question, two answers.** The recogniser re-fires on a long utterance, and the
   same sentence ran twice. `talk.is_repeat` drops an identical transcript within 8 s;
   saying "louder" twice on purpose still works.

And a fifth, in the other direction: a follow-up said while an answer was still being
written used to be **thrown away** ("Still working on the previous request…"), so the
person naturally said it again. `Agent.ask()` now keeps the newest pending request and
starts it the moment the current one finishes.

The rules live in `arcdesk/wake/talk.py` as pure functions (`listen_state`,
`said_myself`, `is_repeat`) so `tests/test_talk.py` can prove every edge without a
microphone.

## Which one do I run — the .exe or JARVIS.bat?

**One route: the folder you already have.** `JARVIS.bat` starts it, `UPDATE-JARVIS.bat`
updates it with a single downloaded zip, and the `.exe` exists only for people who will not
install Python. `WHICH-ROUTE.md` has the table and the list of things to stop doing (each of
them is a "it stopped or errored" you have already hit once).

## check.bat failed in five places on Windows

None of them were the app. `check.bat` and the suite were written on Linux and assumed it:

* **`AttributeError: module 'os' has no attribute 'killpg'`** — step 1/9 died before a
  single test ran. `os.killpg` is POSIX-only; `tools/voice_roundtrip.py` and
  `tools/smoke_firstrun.py` now stop a child through one `_stop_child()` helper that uses
  `terminate()` on Windows.
* **`test_backup`** created a symlink, which Windows refuses without developer mode/admin →
  the case is skipped there, with a line saying so.
* **`test_clean`** asserted ffmpeg exists. This app does not need ffmpeg any more
  (`arcdesk/audio.py`), so it skips and says why.
* **`test_clone`** checked the old "ffmpeg is needed" sentence and, worse, could start a
  real `pip install` from inside a test. `ARCDESK_NO_DECODER_INSTALL=1` forbids that, and
  the assertion now matches what the app actually says.
* **`test_engines`** used hard-coded `/tmp/...` paths. It uses a real temp folder.

`check.bat` itself now ends with a count and three next steps instead of forty screens of
output, and points at `.failures\<test>.txt` for the exact failing line.

## `Unable to find type [IO.Compression.ZipFile]` when updating

The updater's first version asked PowerShell to open the downloaded zip. On a default
Windows PowerShell that type is not loaded until its assembly is, so the call failed — and
the updater then decided "that zip is not the app" and refused a perfectly good
`ArcDesk-full-project.zip`. Not a download problem, not a wrong file.

Since fix38 `UPDATE-JARVIS.bat` uses, in this order:

1. **the app's own Python** — `python tools\update_from_zip.py "<zip>"`. `zipfile` cannot
   fail that way, it skips `.venv` and `settings.json` by name, and it is the same code
   JARVIS can run itself.
2. **tar.exe + robocopy**, both shipped with Windows, when there is no `.venv` yet. The
   zip is listed to a temp file first (no nested-quoted pipe), the root `run.py` is the
   proof that it is the app, and `robocopy /XD .venv` copies the rest.
3. PowerShell, only as a last resort, **with** `Add-Type -AssemblyName
   System.IO.Compression.FileSystem` so the type really exists.

Either way:

* a **fix pack** (no `run.py` at the root) is refused before anything is copied;
* a failed unpack or copy leaves the old version working, and says so;
* the file `jarvis-update-log.txt` records every step.

You can also do the same job from the app's own Python, which is handy when the `.bat`
is the thing misbehaving:

```
.venv\Scripts\python.exe tools\update_from_zip.py --check     :: what it would do
.venv\Scripts\python.exe tools\update_from_zip.py            :: newest zip, apply it
.venv\Scripts\python.exe tools\update_from_zip.py C:\path\new.zip
```

## "That zip is not the app: there is no run.py inside it" — on a fix pack

The updater was telling the truth and still being useless: it searched Downloads for
`arcdesk-fix*.zip`, found one, and then refused it because a fix pack has no `run.py`.
Offering something you will refuse is worse than not offering it.

Now the updater knows what it is holding:

| the zip | what happens |
|---|---|
| has `run.py` + `requirements.txt` at the root | **the whole app** — replaces the project |
| carries `FIXPACK.txt`, or ≥2 of its files already exist in this project | **a fix pack** — copied **on top**, which is exactly what a fix pack is for |
| neither | refused, with the reason and what to download instead |

So either download works: the full project zip *or* a fix pack. When both are in
Downloads, the **whole app wins even if the fix pack is newer** — replacing the app is
always right, and a fix pack applied over an older base usually is not what was meant.

Every fix pack built from now on carries `FIXPACK.txt`
(`python tools/make_fixpack.py --name fix40 --files …`), so the decision never has to be
a guess again.

One limit, stated plainly: the **fallback** route (used only when there is no `.venv` yet)
cannot apply a fix pack — there would be no project to patch. It says so and points at the
full zip.

## "I installed the voice clone engine in a terminal, but JARVIS asks me to install again"

Because "installed" means *installed into one particular python*, and there are several on a
Windows laptop. `pip install torch transformers` in a terminal fills up whichever python was
on PATH; JARVIS runs in its own `.venv`, and nothing from another interpreter is visible
from inside it. So the engine really was missing **from the app's point of view** — but
downloading 1.5 GB a second time is not the right answer.

Since fix40 the app does what a person would do: it **finds the python that already has it**
and uses that one.

* `engines.interpreters()` lists every python worth asking — this app's, the app's `.venv`,
  the private engine folder, and the one on PATH.
* `engines.probe_python()` asks each of them a one-line question in a child process
  (`importlib.util.find_spec`), capped at 20 seconds.
* if a foreign interpreter has the engine's packages **and** the weights are in the
  Hugging Face cache, `clone.engines()` marks the engine **ready** with `foreign=<that
  python>`, and `clone.speak()` hands the sentence to it — no second download.
* the engine dialog has a **"Find what I installed"** button that prints the whole report:

```
which python has what (checked just now):
  this app         C:\...\JARVIS\.venv\Scripts\python.exe
                   has: torch, transformers
  python on PATH   C:\...\Python312\python.exe
                   has: nothing relevant
  weights IndicF5    C:\Users\you\.cache\huggingface\hub\models--ai4bharat--IndicF5
```

If nothing has them, the report says so plainly, and the one-line fix is:

```bat
.venv\Scripts\python.exe -m pip install torch transformers soundfile
```

(That is the same install the button does — but sometimes doing it by hand is the fastest
way to see the error, and now the app can also just adopt your existing install.)

## "I install piper (or the other voice engine) and the application just closes"

Two separate causes, both fixed in fix41. Neither one printed anything — that is why it
looked like the app closing itself.

**1. `pip install` was aimed at the environment the app was running in.** `sys.executable
-m pip install …` swaps files under a *live* process, and the big ones pull their own
versions of shared packages (`coqui-tts` pins an older numpy). The next import after that
can die. Since fix41 every engine — piper included — is installed into the app's **private
engine folder** (`%APPDATA%\ArcDesk\engine_env`), made by `ensure_sidecar()`. The app the
person is using never has a single file changed under it, and the frozen `.exe` and a plain
checkout now behave the same way.

**2. Asking "is it installed?" used to IMPORT it.** `__import__("piper")` loads
`onnxruntime`; `__import__("torch")` loads torch's MKL/OpenMP DLLs. Next to Qt's own DLLs
that can abort the process with `OMP: Error #15` and no traceback. Now:

* `clone._importable()` uses `importlib.util.find_spec` — reads the file system, runs nothing;
* `voice.piper_available()` uses `find_spec`, then asks `piper_engine.python_with_piper()`;
* piper **speaks in a child process** (`arcdesk/piper_engine.py`), so a piper problem costs
  one sentence and the voice chain falls through to the next engine.

**And if something native still kills it, there is now a record.** `logs.watch_crashes()`
turns on `faulthandler`, which writes the Python stack to
`%APPDATA%\ArcDesk\logs\fault.log` at the moment of death, and `logs.begin_session()` /
`logs.end_session()` leave a marker: if the last run did not close properly, the next start
puts a line in the console —

```
CRASH · last time JARVIS stopped without closing properly (started …, pid …) —
        that is the moment that needs explaining
```

So "auto close aaguthu" now has a file to point at instead of a guess. Send
`%APPDATA%\ArcDesk\logs\fault.log` and `arcdesk.log` and the last stack in either one
names the import.

**Which interpreter will speak?** The same screen answers it — the engine dialog's **"Find
what I installed"** prints every python on the PC, what each one has, and (for piper) the
one that will actually be used:

```
no interpreter on this PC has piper yet. checked:
  this app         C:\...\JARVIS\.venv\Scripts\python.exe   has: nothing
  python on PATH   C:\...\Python312\python.exe              has: nothing
```

## "Double-clicking JARVIS.bat does nothing / the app stopped opening after I closed the window"

Three separate things, all in fix42, and all of them the same shape: the launcher was
answering the wrong question.

**1. It asked "is *any* pythonw.exe alive?"**
`tasklist /FI "IMAGENAME eq pythonw.exe" | find /I "pythonw.exe"` is true for any python
program on the PC — and for our own copy that had stopped responding. So the launcher
printed *"already running - nothing to start"* and started nothing. The window never came
back, which is exactly the report.
Now the launcher asks the app itself, through `tools/jarvis_state.py`:

```
python tools/jarvis_state.py --wake        # ask the running copy to show itself
python tools/jarvis_state.py --kill-stale  # close only OURS, and only if it is stuck
python tools/jarvis_state.py --any         # is any copy of ours there at all?
python tools/jarvis_state.py --stop        # close ours politely (an updater needs this)
python tools/jarvis_state.py --status      # 0 live, 2 running-but-silent, 1 not running
```

"Alive" means the app's **own lock socket answers** on `127.0.0.1:<port>` — the only proof
that a *working* copy is there. The port comes from `lockport.txt`, which the app writes
when it takes the lock and deletes on the way out (`instance.port_file()`), so a settings
file from another profile cannot mislead it.

**2. Closing the console window could take the app down with it**
`start "" pythonw run.py` keeps the new process attached to the launcher's console, and
closing that console can end it. The launcher now uses PowerShell `Start-Process
-WindowStyle Hidden`, which detaches.

**3. A second launch could exit in silence**
`run.py` printed "Arc Desk is already running — bringing it to the front" and returned
**without sending anything**. If the port was held by a stuck copy, nothing appeared.
Now it calls `instance.another_instance_running(cfg)` (which really sends the wake), and if
the port is held but silent it says so in the log instead of vanishing:

```
BOOT · port 8992 is held but nothing answered. JARVIS is not running properly —
       close it with Ctrl+Alt+Q, or run tools\jarvis_state.py --kill-stale, then start again
```

**And the updater stops killing every python on the machine**: `taskkill /IM pythonw.exe`
became `--any` then `--stop`, which asks the app to quit **over its own socket**
(`{"event": "quit"}`), waits up to 8 s for it to close cleanly, and only kills by pid if it
refuses. The app's answer to that event is a flag the existing 200 ms heartbeat turns into
a normal quit — settings saved, session marked clean.

If it still does not open, the launcher now prints the last 12 lines of
`%APPDATA%\ArcDesk\logs\arcdesk.log` before pausing, so the reason is on screen.

## "'...\arcdesk-fix42-launcher-opens\tools\find_project.bat' is not recognized as an internal or external command"

That line is the whole story: **JARVIS.bat was double-clicked inside the unzipped fix
pack**, not inside the app. A pack is a handful of files, so that folder has no `tools\`
next to it, `call` fails, and the launcher then says "I cannot see the project files".

Fixed in fix43, in three places:

**1. the `call` is guarded, and the launcher looks for the app itself.**
`JARVIS.bat` now checks `if exist "%~dp0tools\find_project.bat"` before calling anything,
and then searches for the one marker that cannot be faked (`run.py` **and**
`requirements.txt`):

```
this folder -> its parents (3 up) -> %USERPROFILE%\JARVIS -> Documents\JARVIS
            -> Downloads\JARVIS -> Documents\GitHub\* -> Desktop\* -> Downloads\*
```

The last three go **two folders deep**, because the real app was at
`Downloads\JARVIS\arcdesk-src` — one level too deep for the old single-level scan.

**2. a pack folder now says what it is, and applies itself.**
If the folder it was launched from is not the project and contains `FIXPACK.txt`:

```
  This folder is a FIX PACK - a few changed files, not the app itself.
  The app is here:
    C:\Users\emera\Downloads\JARVIS\arcdesk-src
  I can copy these files into it now, which is what they are for.
  Your settings and the .venv are never touched.
Apply them and start JARVIS  [Y = yes, N = no]
```

Y → `robocopy` the pack on top (`/XD .venv __pycache__ .git .failures`,
`/XF settings.json FIXPACK.txt README-FIX*.txt`), then start `%PROJ%\JARVIS.bat`.
N → nothing is changed, and it prints the manual copy route. So the worst case of
"downloaded a pack" is now the app opening, not an error message.

**3. packs fold in everything since the last whole build.**
`tools/update_from_zip.py` carries `FOLD_IN` — every file changed since the last
full-project zip (fix37 → fix43, 25 files). A pack built with `tools/make_fixpack.py`
therefore brings an old project *up to date*, not just up to its own round, so there is no
"apply 37, then 38, then 39" stack to get wrong. `tests/test_launcher_state.py` checks the
list contains the launcher and the finder, and that every file in it really exists.

`tools/make_fixpack.py --launcher` also ships `JARVIS.bat` and `tools/find_project.bat`
inside the pack, which is what makes the pack-folder case work at all.

## "Romba confuse — which folder is JARVIS? It still does not open"

Six downloads, six folders, all of them called something like `arcdesk-fix42-...`, and no
way to tell which one is the app. `tools/one_place.py` answers it once:

```bat
.venv\Scripts\python.exe tools\one_place.py            :: show every copy, change nothing
.venv\Scripts\python.exe tools\one_place.py --apply    :: keep ONE, park the rest
.venv\Scripts\python.exe tools\one_place.py --undo     :: put them back
```

* a folder counts as the app only when `run.py` **and** `requirements.txt` are both in it —
  the same test the launcher uses, so a fix-pack folder is never mistaken for the app;
* it looks two folders deep in `Downloads`, `Documents`, `Desktop`, `OneDrive\Desktop`,
  `Documents\GitHub` and `%USERPROFILE%\JARVIS`, which is how
  `Downloads\JARVIS\arcdesk-src` gets found;
* the winner is: a copy already at `%USERPROFILE%\JARVIS`, else the one with a working
  `.venv`, else the newest;
* `--apply` moves the winner to `%USERPROFILE%\JARVIS` and every other copy to
  `%USERPROFILE%\JARVIS-OLD\<name>`, recording a manifest so `--undo` restores the exact
  paths. **Nothing is deleted.**
* it refuses to move the copy it is running from (that is the difference between a tidy-up
  and a disappearance) unless `--force` is passed.

Afterwards there is one thing to double-click: `%USERPROFILE%\JARVIS\JARVIS.bat`. See
`ONE-FOLDER.md` for the folder tree, what belongs at the root, and the GitHub Desktop
question ("only the .py files upload").

## The magic screen, explained

It is one full-screen window, and now it says so on itself. Six **strands** leave the
centre, one per thing you can open, and each strand carries its own sentence:

| strand | what clicking it does |
|---|---|
| FILES | your folders, opened in here |
| NOTEPAD | write something, stays in here |
| CALC | quick maths, no spreadsheet |
| TASK MGR | what is running right now |
| SETTINGS | voice, wake word, the rest |
| BROWSER | the web, as a normal window |

The centre says `JARVIS` and one line under the circle says what it is doing **right now**
(`reading your voice clip`, `tool · list_downloads · 1.4 s`). Bottom left is
`WHAT JARVIS HAS DONE` — the last four finished steps with their timings, read from the
activity record, so it cannot show work that did not happen. Bottom line:
`CLICK A STRAND · TYPE BELOW · SAY "BYE JARVIS" · ESC = BACK TO NORMAL`.

What was removed, and why: the hologram globe, the big clock and the six unlabelled tiles.
They were the reason for *"ena nadakuthu nay enakku puriyala ... romba complicate web
mathiri iruku"* — decoration where an explanation was needed. Nothing was lost: the
strands are the same six apps, painted instead of being widgets, so the picture and the
click target are the same rectangle.

## "Correct aana files ah epdi kandupidikaradhu?" — which copy is the real one

Three answers, cheapest first, and the third one is not a guess:

1. **by eye** — the app folder has `run.py` + `requirements.txt` + `JARVIS.bat` at the top.
   A folder named `arcdesk-fixNN-...` or containing `FIXPACK.txt` is not the app;
2. **by its environment** — `\.venv\Scripts\python.exe` exists, so it has actually run on
   this machine;
3. **by asking the running app** — `tools/jarvis_state.py --where` prints the folder whose
   `run.py` the live process is executing (`running_project()` reads the process command
   line, quoted or not, Windows or `/proc`). That folder *is* the correct one.

`tools/one_place.py` uses all three: `running_copy()` validates what `--where` says (the
folder must exist and must really be the app), then it marks that copy `RUNNING NOW` and
`<-- keep this one` in the report, and `--verify` runs the keeper's own interpreter once
(`import arcdesk`) so "it runs" is proven rather than assumed:

```bat
.venv\Scripts\python.exe tools\one_place.py --report "%USERPROFILE%\Desktop\JARVIS-SCAN.txt"
.venv\Scripts\python.exe tools\one_place.py --apply --verify
```

Colour-coded route for a person in a hurry: double-click **`ONE-PLACE.bat`** → it scans →
prints the list → asks one question → prints the single file to double-click from then on.

One rule that matters: when the keeper is the copy the tool is running from, it is
**copied** (`copy_project`, without `.venv` — an environment holds absolute paths) and
never moved. Moving the folder a live process is standing in is the exact failure this
whole round exists to stop.

## `ERROR : Invalid Parameter #1` from robocopy (screenshot 17.png)

```
robocopy "C:\Users\emera\Downloads\arcdesk-fix45-..."  ...
ERROR : Invalid Parameter #1 : "C:\...\arcdesk-fix45-one-place-and-correct-files" ...
```

One cause, and it is a classic: **`%~dp0` ends with a backslash.** So

```bat
robocopy "%~dp0" "%PROJ%" /E ...
```

becomes `robocopy "C:\...\pack\" "C:\...\app"` — the trailing `\` escapes its own
closing quote, Windows' argument parser keeps reading, and robocopy receives the **whole
line as a single argument**. It then prints the entire thing back as "Invalid Parameter #1"
and copies nothing.

Fixed in fix46, twice over:

1. **the launcher** strips the backslash before using the path:
   ```bat
   set "SRC=%~dp0"
   if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
   ```
2. **it does not use robocopy at all when the app's Python is there** — it calls the
   updater that has tests, with a new mode for an unzipped pack:
   ```bat
   "%PYU%" "%UPD%" --folder "%SRC%"
   ```
   `update_from_zip.copy_folder_over()` copies the pack on top with the same skip rules as
   a zip: `.venv`, `settings.json`, `FIXPACK.txt`, `README-FIX*`, `__pycache__`, `*.pyc`.
   robocopy remains only as the fallback for a project with no `.venv` yet.

And `tools/batlint.py` now refuses this shape on sight:

```
[FAIL] break.bat
       break.bat:2 passes "%~dp0" (it ends in a backslash) as an argument — the closing
       quote is escaped and the command gets one argument.
       Use set SRC=%~dp0, strip the last character, pass "%SRC%"
```

`cd /d "%~dp0"`, `pushd "%~dp0"`, `call :label "%~dp0"` and `if exist "%~dp0..."` are all
still fine — they never hand that string to a program that parses quotes.

## "JARVIS is running" — and no window (screenshot 18.png)

```
project folder : C:\Users\emera\Downloads\ArcDesk-full-project\tools\..
...
starting JARVIS - it runs in the background with no window, by design.
JARVIS is running.
```

It was telling the truth, and that was the bug. `JARVIS.bat` started the app with
**`--shadow`**, which is the stealth flag: the process runs, the tray exists, and no window
is ever shown. So a double-click looked exactly like a failure.

Since fix47:

* **a double-click shows the window** — the launcher passes `--show`, and `run.py` treats
  that as "somebody is at the screen" (`cfg["_force_show"]`, which `MainWindow` already
  honoured).
* **stealth is still the resting state where it belongs** — the Start-with-Windows entry
  (`arcdesk/autostart.py`) and the wake daemon pass `--shadow` themselves, so the copy that
  starts at login stays invisible until "hey jarvis".
* the closing message says so: *"JARVIS is running - the window is open now … if you cannot
  see it, look on the taskbar, or press Ctrl+Alt+J."*

Proven both ways, in one sandbox with `shadow.enabled = true` already in settings:

```
python run.py --show    -> BOOT · the window is shown
python run.py --shadow  -> BOOT · stealth: the window is not shown (that is what --shadow asks for)
```

**And the path is no longer written with `\tools\..` in it.** `find_project.bat` and
`JARVIS.bat` both normalise it now:

```bat
for %%I in ("%PROJ%") do set "PROJ=%%~fI"
```

so the launcher prints `C:\Users\emera\Downloads\ArcDesk-full-project`, which is the
folder somebody can actually go and look at.

## `install_clone.bat`: forty lines of traceback, then "retry with internet" (21.png)

The screenshot is a cmd window ending in

```
OSError: You are trying to access a gated repo … 401 Client Error
Access to model ai4bharat/IndicF5 is restricted …
(IndicF5 download failed - retry with internet)
Install XTTS-v2 for English cloning (~1.9 GB) [Y,N]?
```

Three things were wrong, and the first one was hidden in the other two:

1. **The diagnosis.** "Retry with internet" sent the person to check their wifi for a
   licence problem. The model is **gated**: the licence has to be accepted once and a
   Hugging Face token supplied. Retrying never works.
2. **The check that should have caught it was asking the wrong URL.** Measured on
   2026-10-25:

   | URL | answer |
   |---|---|
   | `huggingface.co/api/models/ai4bharat/IndicF5` | **200** — metadata is public |
   | `huggingface.co/ai4bharat/IndicF5/resolve/main/` + the model's own `config` file | **401** — the *file* is gated |

   `engines.gate()` asked the metadata API, so it answered "no licence needed", the script
   installed 200 MB of torch, and the first file downloaded with a traceback. It now probes
   a **real file** (`GATE_PROBE_FILE = "config.json"`), which is the only thing that answers
   the question being asked.
3. **The output.** A traceback is not an answer. Every line the .bat prints now comes from
   `tools/engine_get.py`, the same code path the app's dialog uses — so the terminal and the
   app can never disagree.

What the script does now, in this order:

* prints `engine_get.py status` — what is installed, how big, and whether a token is saved;
* **English first**: XTTS-v2 (~1.9 GB) needs no account;
* then `engine_get.py gate indicf5`; if it is gated, it explains the two clicks and offers
  `set /p` to paste the token (saved through the app's own settings, never printed, never
  logged), then re-checks;
* only then offers the IndicF5 download;
* Piper (~60 MB, no account, no GPU) is named up front as the quick answer.

Also in this fix: `JARVIS.bat` and `install_clone.bat` now say one line when the folder they
are running from is inside **Downloads** — that is how `JARVIS-ready (1)` happened, and two
copies is how "which one is the real JARVIS?" happens.

`tests/test_install_clone_bat.py` keeps all of it: no inline `python -c` downloads, the gate
asked before the download, the token offered, no "retry with internet", and the helper's own
exit codes (0 done · 1 failed · 2 needs a token).

## Settings opens and hangs with a spinner (screenshot 20.png)

Not a network problem and not the microphone: the dialog was asking a question that costs
**child processes**, on the thread that draws it.

```
SettingsDialog._refresh_voice_status()
  -> clone.engines()
     -> _foreign_python()            (added in fix40: "use an engine you already installed")
        -> engines.find_engine_python()
           -> starts a python per candidate interpreter, 20 s cap, for each engine
```

Two smaller versions of the same mistake sat next to it: `_module_ok()` answered "is it
installed?" with `__import__(name)`, and the reply-voice sentence was computed inline.

Fixed in fix48:

* `engines.foreign_cached(engine)` — **cache only**, never blocks. Cold cache answers `""`
  and starts `warm_foreign()` in a daemon thread, which stores the answer for ten minutes;
* `clone._foreign_python()` calls that, so `clone.engines()` is now a file-system question;
* `SettingsDialog._module_ok()` uses `importlib.util.find_spec` — the file system, no
  import, so a native library is never loaded to answer yes/no;
* the reply-voice line says `checking…` and arrives through a **signal** from a worker
  thread (a `QTimer.singleShot` scheduled from a worker has no event loop and sometimes
  never fired), so Cancel and Save are always live.

Measured, all three dialogs in a row: **101 ms / 115 ms / 127 ms** to build, `_refresh_voice_status()`
**0 ms**, and the sentence fills in a moment later:
`Reply voice: the system voice — no reply voice added yet (Settings → Voice).`

### …and the round after that: the busy ring that never stops (the same screenshot again)

fix48 fixed the *one* path that was named. The report came back with the same picture, and
this time the honest answer had to be a rule rather than a patch — because a screen that
says "waiting" for ever can only be two things:

1. **work on the drawing thread.** A `subprocess`, a socket, a download or a `sleep` inside
   a click handler stops the event loop: no repaint, no Esc, no Cancel.
2. **a waiting cursor nobody put back.** `QApplication.setOverrideCursor(WaitCursor)` with
   no matching `restore` is literally the spinning ring in the screenshot.

fix49 therefore adds two modules and moves every remaining offender onto them:

| what | where it lives now |
|---|---|
| one way to wait | `arcdesk/uiwork.py` — `run()` (worker + signal back to the UI thread), `busy_cursor()`, `clear_stuck_cursors()`, `StallWatch` |
| one way to catch it again | `arcdesk/blockguard.py` — logs (or `ARCDESK_UI_GUARD=strict` raises) when something that waits runs on the drawing thread, naming `file:line in function <- who called it` |
| the dialog that asks every python | `EngineDialog.reload()` / `_scan()` — worker, list fills in when the answer arrives, install button disabled until it knows |
| reading a voice clip | `VoiceLibraryDialog._busy()` — worker; buttons disabled meanwhile; Esc and Done stay live |
| the HUD's "local engines" row | `brain.status()` — cached on the main thread, a worker takes the fresh answer |
| "Auto" in the AI page | `ollama_alive()` — the page says `Ollama detected: checking…` and the answer arrives by signal |
| the backend scan in Settings and the Welcome card | `uiwork.run` (it was a thread writing to widgets — Qt does not allow that) |
| MCP boot, audit, wallpaper, background jobs | `uiwork.run` — they used `QTimer.singleShot(0, …)` **from a worker**, which never fires: the line they were supposed to print never appeared |
| quitting | the launcher watch is a real `QEventLoop`, not `processEvents()` + `sleep` |

And so that the next report contains the answer instead of the question, the log now says
which line froze the window:

```
UI · the window was frozen for 2.3 s — main thread was in widgets/window.py:1237 in _arm_launcher
```

`tests/test_no_freeze.py` proves it with the freeze made real (the engine probe is slowed to
1.2 s on purpose): Settings builds in **64 ms**, the engine dialog in **3 ms**, "Find what I
installed" returns in **1 ms**, a 1-second voice upload returns in **0 ms**, and Esc closes
each of them while the work is still running.

`tests/test_ui_never_blocks.py` keeps it that way: a 1.5 s fake probe must answer the
caller in under 100 ms, 100 more calls must start no probe at all, and a module that raises
on import must still answer "installed" without being executed.

---

## The window says "(Not Responding)" for minutes, then the app is gone (28.png)

Not "slow" — **Not Responding** — and it came back right after "Hear the reply voice"
worked (the line *had* painted: "spoke via your clip, exact clone (indicf5) — en"), so
the window was already alive and then something on the drawing thread stopped answering.

Two things on the drawing thread could each take minutes on a machine that already has
the engines installed (which is exactly this machine — indicf5, xtts and piper were
installed in a terminal):

| what was wrong | where | what it cost |
|---|---|---|
| the status card refreshes every 10 s and its voice line asked `clone.engines()` for a *fresh* answer — a cold cache means "ask every python on this PC what it has", and each answer imports the engine's libraries | `widgets/window.py` → `_refresh_status_card` → `SettingsDialog.reply_voice_line` → `clone.engines()` | 30-90 s per interpreter, several of them, once every ~30 s |
| the accent note under "Hear the reply voice" called `voice_names()`, whose first call in a process is a PowerShell `GetInstalledVoices` probe | `widgets/settings.py` → `_refresh_voice_note` → `voice.voice_names()` | up to 12 s, on the thread that draws the dialog |

The "auto close" was not the app quitting itself — it was Windows (or the finger) giving
up on a Not Responding window. The app had no timer that kills it; it simply could not
answer.

The rule now, held by `tests/test_no_gui_probe.py`:

* **the drawing thread only reads.** `clone.engines(cached_only=True)` answers from the
  cache — cold means "the last known state" (or an honest "checking…"), never "go ask
  every python". The status card is the first to obey.
* **the voice list is a one-time background cost.** `voice_names_cached()` says whether
  we know yet; `voice_names_ensure()` pays for the probe, and start-up pays it (a daemon
  thread in `run.py`, `arc-warm`) — the accent note shows "checking the installed
  Windows voices…" until the answer arrives by signal.
* **the engine sweep also happens once in the background**, 40 s after the window is up,
  so the card's voice line becomes the real one within a minute — while nothing competes
  with the boot.

## "Whatever I do, JARVIS just closes" — and the crash report that answered it

Not a hang this time: the process died with a native access violation, and
`crash-report.txt` (written automatically, in the app's data folder) carried the
faulthandler stack:

```
Current thread … (most recent call first):
  File "…\arcdesk\widgets\window.py" in eventFilter
  File "…\arcdesk\widgets\safeopen.py" in open_dialog     ← dialog.exec()
  File "…\arcdesk\widgets\window.py" in open_settings
  File "…\arcdesk\widgets\window.py" in _show_quick_menu  ← the right-click menu
```

So the window was fine, Settings was open, and the memory manager killed the process
somewhere in the hottest C call in the app. The log next to it carried the fingerprint:
`QThreadStorage: entry … destroyed before end of thread` — mid-session, on a worker
thread. That warning is a known Qt defect (regression in Qt 6.8.2, present again in
6.10.0–6.10.2, fixed in 6.10.3 / 6.11.1 / 6.12.0): Qt destroys a global per-thread
store while a thread is still alive, the heap is quietly corrupted, and the process
dies later, in a random hot spot, with no traceback.

The app used to install "whatever PyPI gives" (`PySide6-Essentials>=6.6,<7`), so the
Qt the machine ended up with was a roll of the dice. What changed:

| what | where |
|---|---|
| the Qt is now a **pinned, tested version** (`PySide6-Essentials==6.12.0`, the fixed one the test farm runs) — no more dice | `requirements.txt` |
| the crash report and the boot log now say **which python, which Qt, which machine** died — the next report answers the version question by itself | `arcdesk/logs.py` (`env_line`), `run.py` |
| the filter's hot path makes **no C++ virtual call** (the base class has no filter of its own; `False` is the whole answer) — one less hot spot for a heap fault to land in | `widgets/window.py` |
| a worker's answer-bridge can no longer be destroyed from a worker thread (it lives under a process-lifetime parent), and a finished worker is unregistered only after its thread has truly stopped | `arcdesk/uiwork.py`, `widgets/qsafe.py` |
| a background voice-list probe that finished into a closed dialog no longer emits into the void unguarded | `widgets/settings.py` |

If it happens again: send `crash-report.txt` as it is — the environment line at the top
tells the story the last one could not.

## The window vanished, but `pythonw.exe` is still in Task Manager

That is not a crash. Closing the window (X or Esc) hides JARVIS into the system
tray — it keeps listening, and being hidden is its resting state. The process in
Task Manager is the still-running app, not a leftover. The tray shows a notice the
first time this happens, and the log says

    UI · the window was closed - JARVIS is not closed, it is running in the tray.

* **I want it back:** `Ctrl+Alt+J`, or click the tray icon.
* **I want it really closed:** `Ctrl+Alt+Q` (or tray → Quit).
* **There are several `pythonw.exe`, from several folders:** the zip was unzipped
  more than once and each copy was started once. `KILL-JARVIS.bat` (in the JARVIS
  folder) closes every copy from every folder in one click — by pid only, never by
  name, and never touching settings, voice clips or documents (those live in
  `%APPDATA%\ArcDesk`). After that keep ONE folder (`ONE-PLACE.bat`) and delete
  the rest.

`JARVIS.bat` does the smaller version automatically: before it starts, it closes
copies that came from *other* folders (they hold the window lock and steal the
wake, which is what a double-click with no window is).

## check.bat says "8 FAILED" on a healthy laptop

Running the suite on the real machine (that is what check.bat does) turned up
failures that had nothing to do with the build — the tests were measuring the
*laptop*, not the code. A suite that goes red because Ollama happens to be running,
because the timezone is not UTC, or because the disk is slow cannot be trusted, so
each one was made hermetic:

| test | what it was measuring instead | the fix |
|---|---|---|
| `test_nudge` | the machine's timezone (its "2 a.m." was computed in UTC; in Calcutta that is 07:30, which is not quiet) | the fake times are built from the local clock |
| `test_app_lifecycle` | a fake socket option `0x4` — which is exactly `SO_REUSEADDR` on Windows, so the "no SO_REUSEADDR" check matched its own fake, and the "second copy refused" check set the *permissive* flag | the fake is now the real `SO_EXCLUSIVEADDRUSE` value (257) |
| `test_one_place` | Windows' temp lives under `AppData\Local\Temp`, and one string filter ignored the "the home itself is a temp folder" exception — the test's own copies were dropped as trash | `is_temp` now lets the whole search stand when the home is in temp |
| `test_backends` | the laptop's real Ollama on 11434 (honest answer: prefer it — but not the answer the fake-server experiment asks) | the probe is restricted to the fake's own port, and the list is restored |
| `test_mcp_presets` | whether uvx/npx happen to be installed (without them nothing is enabled and the config shape check ran out of list) | the runner check is stubbed for the merge logic; skips are verified in both hermetic worlds |
| `test_backup` | the **real** start-with-Windows entry — on Windows the store is the HKCU registry, which no test override can reach; the final `disable()` would have *removed the person's real entry* | the stand-in store (`ARCDESK_AUTOSTART_FAKE`) is forced on |
| `test_holo` | the CPU's speed — a real laptop measured 98 ms/frame against a 22 ms 30 fps budget, blank frames at 0.2 ms | a machine that cannot hold 30 fps reports the measured rate and the graceful degradation instead of failing the build; every correctness check still runs |

The rule they all share: **a test either builds its own world or it stubs the seam it
cannot build** — never reads the laptop that happens to be running it. And nothing a
diagnostic runs may *change* the machine: the one place it used to (the registry) now
goes through the stand-in.

## "Laptop on pannina JARVIS start aagala" — auto-start was on and still started nothing (2 fixes)

Two separate holes, both silent.

**It was never on for a new copy.** Turning it on lived in one checkbox inside Settings, so a
fresh unzip started by itself exactly never — and "restart pannina automatic ah start aaganum"
stayed a wish. Now the **first launch switches it on** (`autostart.ensure_first_time()`), says
so in the console, and never asks twice. It stays reversible in three places: Settings, the
tray menu, and `AUTO-START.bat` — and once you switch it off, nothing turns it back on.

**A re-unzip broke it without a single visible sign.** The zip unpacks to `JARVIS-ready (1)`,
so the registered command still pointed at `JARVIS-ready\JARVIS\run.py`, a folder that no
longer existed. The entry was there, Task Manager said "enabled", `is_enabled()` said True,
and Windows started nothing. Worse, the check that was supposed to catch this only looked at
the **first** token of the command — `pythonw.exe` — which of course still existed. Now:

* the command line is split with quotes respected (`_split_command`), so a path with a space
  is never mistaken for a program;
* **both** the interpreter *and* `run.py` are checked, and the reported `exe` is the script —
  the thing that actually moved;
* `repair()` fixes a stale entry **only if it is already on**, and **boot calls it** every
  launch (`AUTOSTART · repaired|fine|off` in the log). Unzip again, start once, and it points
  at the new folder by itself. If it is off, boot leaves it off: that is a choice, not a bug.

**And it now starts background, not in a black window.** `launcher()` uses
`pythonw.exe run.py --shadow` — no console, no window, no tray until you call for it.
`Ctrl+Alt+J` opens it, `Ctrl+Alt+Q` quits.

The double-clickable version is `AUTO-START.bat` (state, on, off, repair — prints the exact
folder it will register before it registers it, and never needs an administrator);
`tools/autostart_set.py` is the same thing from a terminal, and it is the same code the
Settings checkbox calls, so the three can never disagree.

`tests/test_autostart_repair.py` proves all of it against a redirected store: the launcher is
`pythonw` + `--shadow` + an absolute path, a path with a space stays quoted, `enable()` reads
itself back, `disable()` twice is still fine, the first offer is remembered, `repair()` is a
no-op when off and "fine" when healthy, a ghost path (`JARVIS-ready (1)`) is reported stale and
then repaired to the folder the app is running from — and `run.py` calls `repair()` but never
`enable()`.

## "Spider web la task click pannina app hang aaguthu" — the click path, three causes

Clicking a strand on the magic screen did nothing and the whole deck froze.

1. **TASK MGR** called `psutil.process_iter()` **on the drawing thread**, from the dock's
   constructor. On Windows, behind antivirus, that is seconds. The click was accepted, no
   repaint happened, and the deck sat there — a hang, exactly as reported.
2. **SETTINGS** ran `open_app` — a child process — on the drawing thread, and then its dialog
   could land behind a fullscreen always-on-top deck.
3. **BROWSER** launched a real window that appeared *behind* the deck: a click that worked
   looked exactly like a click that did nothing.

Now: the dock builds in **~10 ms** with a placeholder line; `refresh()` reads the process
table on a `uiwork` worker (`arc-dock-processes`), disables its own button, says
"reading the process list… (the deck stays usable)", and fills the list when it arrives. A
failing read prints a line instead of freezing. Every Windows/web strand leaves the deck
**first** — `exit_magic(farewell=False)`, because the goodbye path routes through
`_apply_bye_action`, which can quit the app — then launches on a worker (`arc-magic-open`)
and raises the window after 900 ms. `SETTINGS` opens JARVIS's own settings, not a Windows
settings page. Every click is narrated on the deck's status line and in the console.

`tests/test_magic_click.py` proves it with the slowness made real: the process table is
slowed to 1.0 s and the click still returns in **2 ms** while the deck keeps painting
(40+ repaints during the read); a launch is slowed to 0.8 s and the click returns in **1 ms**
with no block-guard hit; the deck is left before any launch, never with the goodbye; the six
painted strands all answer a click at their own centre; and the source keeps
`process_iter(` in exactly one place, inside `_read_processes`, driven by `uiwork.run`.

---

## "JARVIS.bat double-click panna terminal open aaguthu, app varala" — four causes, one launcher

Reported repeatedly, in almost the same words each time. It was never one bug: it was four
different failures that all looked identical, because the launcher treated *"the message was
sent"* as proof that a window existed.

**1. The wake was fire-and-forget.** `jarvis_state --wake` and `run.py`'s second-launch path
both returned success the moment the bytes left the socket. So a hung copy, a copy still
building its window, and a copy that ignored the event were indistinguishable — and the
launcher printed *"JARVIS was already running — brought it to the front"* over an empty
desktop. Now the app **answers**: `instance.ask()` waits for a reply (`awake` / `bye` /
`ignored`), `wake_now()` retries three times over ~1.5 s (a wake that lands while the first
copy is still building its window is otherwise dropped), and the launcher goes one step
further than an answer — it waits for the app's own log line
`WAKE · the window is in front`, which is written on the GUI thread *after* `show()`.

**2. The wake showed a cinematic, not the app.** `summon()` went through `_on_wake()` →
`awaken()`, which **hides** the window and shows a fullscreen arrival clip. When that clip
cannot draw — a remote session, a VM, a driver hiccup, a laptop driving a second screen —
the result is *no window at all* while the process sits in the tray. `summon()` now calls
`show_now()`: un-minimise, show, raise, focus, deck included. The cinematic stays where it
belongs, on the wake word.

**3. The wait was silent.** Up to 30 seconds of a blinking cursor, then either a cheerful
sentence or a log dump. `tools/launch.py --wait 25` prints a line every second and returns
the moment a window is proven. The retry is bounded (three tries), so it can never spin.

**4. A crash explained nothing.** `pythonw.exe` has no console — the traceback went into a
log and the launcher window closed over the only clue. `tools/launch.py --diagnose` now
runs numbered checks in the launcher's own window and then prints the app's last lines:

```
   1. [PASS] run.py is here  —  C:\Users\emera\JARVIS\run.py
   2. [PASS] a Python to run it  —  ...\.venv\Scripts\pythonw.exe
   3. [PASS] settings folder is writable  —  C:\Users\emera\AppData\Roaming\ArcDesk
   4. [FAIL] PySide6 imports in that Python  —  No module named 'PySide6'
   5. [PASS] psutil imports in that Python  —  7.2.2
   6. [PASS] the log can be written

  verdict: broken install
  what to do, in order
   1. run: .venv\Scripts\python.exe -m pip install -r requirements.txt
```

One more trap was found while fixing this: the line `BOOT · stealth: the window is not shown`
— written at every login by the copy Windows starts in the background — had been listed as
proof that a window exists. It says the opposite. A launcher waiting for that would have
been told "yes" by the line that says "no", at exactly the moment the person was staring at
an empty screen. It is excluded now, and a test pins it.

**What a double-click does today, in order:** find the folder → fetch Python if needed →
build `.venv` if needed → is a copy answering? (acknowledged wake, then a *proven* window)
→ if not, start one and wait with a visible counter → if no window, print the checks and the
log tail, and **keep the window open**.

`tests/test_open_every_time.py` keeps all of it: a real `Instance` acknowledges a wake while
a socket that accepts and stays silent does not; `summon()` makes a hidden window visible
without touching `Awakening` and writes the launcher's marker; a marker from an hour ago is
rejected while a fresh one is accepted; `crash_reason()` finds `No module named 'PySide6'`
rather than the last line; `launch.py --wait` exits 1 with progress lines when nothing comes
up and 0 when the app proves it did; `--diagnose` prints numbered PASS/FAIL and a verdict;
`run.py` returns 3 for "port held but dead"; and `JARVIS.bat` uses every one of those, with
`pause` still keeping the window on screen when it fails.

---

## "Still waiting for the window" for 25 seconds, then "trying again" — the second pass (23.png)

The launcher was honest but useless: it printed a counter for 75 seconds and then gave up,
because it had **never looked at the process it started**. Two things follow from that:

1. **It could not tell "slow" from "dead".** `pythonw.exe` has no console and no stderr; a
   crash at import time left nothing behind — the app was gone in 0.8 s and the launcher
   kept counting to 25. Now the child's own output goes to
   `%APPDATA%\ArcDesk\logs\spawn.log`, its **pid is remembered**, and the wait checks the
   pid every second. A crash reads like this, in about one second:

   ```
   4. waiting for a window (it writes a line the moment one is up)
      it exited after 1.0 s, before any window
     verdict: started, then closed itself
     what the started process itself said
     ModuleNotFoundError: No module named 'PySide6'
   ```

2. **It printed instructions instead of repairing.** A voice-engine install can take
   PySide6 with it (torch pins an older `typing-extensions`, or a wheel is replaced
   mid-install) — and the app then dies before it can draw anything. The launcher now runs
   the repair itself, in the app's own environment, saying what it is doing:

   ```
   1. checking this install
      not right yet: PySide6 imports in that Python
      repairing: python.exe -m pip install -r requirements.txt
      (one time, a minute or two, needs internet …)
      repaired — the libraries import again
   ```

   That is the rule from earlier reports, kept everywhere: **never ask a person to run
   something the app can run.**

Two smaller lies were removed at the same time:

* **"A line in the log" is now counted in bytes, not seconds.** Run the launcher twice in a
  minute and the second run found the *first* run's `BOOT · the window is shown` line and
  reported success over an empty screen. `open_now.window_mark_from(offset)` only accepts
  lines written after the current attempt started.
* **The wake path is verified, then replaced if it lied.** If a running copy acknowledges a
  wake and no window appears within 6 seconds, it is closed and a fresh copy is started —
  instead of a cheerful message over a blank desktop.

`JARVIS.bat` now hands the whole job to `tools\launch.py --ensure --wait 25`, which does, in
order: preflight (six checks) → repair if a library is missing → wake a live copy and verify
its window → close a stuck copy of *ours only* → start with output captured → wait for proof
→ or print the numbered checks, the child's own traceback, and the app's last log lines, in
a window that stays open. The old plain `Start-Process` start is kept as a fallback for a
copy that has no `launch.py`.

`tests/test_open_every_time.py` covers it: a crashing install must fail in seconds with the
child's own words and the verdict `started, then closed itself`; an older log line must not
prove a newer window; and `--ensure` on this checkout must really start the app, prove the
window, and be closable again.

One more thing that surfaced while testing this: `engines.probe_python` treated **a probe
that timed out** the same as **a probe that said no**. On a busy laptop (antivirus scanning
a torch import) a perfectly installed engine could be reported missing mid-sentence, and
the reply then fell back to a stock voice. A timeout is not evidence of absence:
`_PROBE_TROUBLE` now records it, and `find_engine_python()` keeps the last true answer
instead of overwriting it with "not installed".

---

## `check.bat` on Windows reported seven failing tests — four of them were the checker's fault

The screenshot (25.png) was honest and unhelpful at the same time:

```
FAIL test_app_lifecycle   FAIL test_autostart_repair   FAIL test_backends
FAIL test_backup          FAIL test_clone              FAIL test_docs      FAIL test_firstrun
```

Three of those were **the test harness measuring the wrong thing on Windows**, and one was a
test that *changed the machine it was measuring*. Both are fixed; the rest need one file to
diagnose, which is what check-report.txt now is.

**`[2/9]` could never pass on Windows.** `tools/smoke_firstrun.py` asked "did it shut down
cleanly (exit 0)?" — after calling `proc.terminate()`. On Windows that is
`TerminateProcess`: exit code 1, no shutdown, no message. So the app was reported as failing
to close cleanly when it had never been *asked* to close. It now asks through the app's own
instance lock (`jarvis_state.ask_to_quit`), which is the same channel "bye jarvis" uses, and
reports `exit 0` and `closed cleanly` honestly. `check.bat` also stops passing
`--no-instance` for that section, because a copy with no lock socket cannot be asked — only
killed, which is exactly the measurement that was lying.

**`test_autostart_repair` registered JARVIS at login on the machine running it.** The test
has to write an autostart entry to prove that a *stale* one gets repaired — and on Windows
that meant the real `HKCU\...\Run` value. A test must never change the machine it is
measuring. `ARCDESK_AUTOSTART_FAKE=1` now redirects the entry to a small JSON file
(`autostart._fake_path()`), so the whole repair story — off ⇒ no-op, healthy ⇒ fine, ghost
path ⇒ repaired, off again ⇒ stays off — is provable without touching the person's laptop.

**check-report.txt (written next to check.bat by tools/failure_report.py) is what to send when something still fails.** `tools/failure_report.py`
writes one text file with the failing check lines from `.failures\`, the exception if there
was one, the Windows build, the Python, the free space on the JARVIS drive, and the last
lines of the app's own log *and* of the started process (`logs/spawn.log`). `check.bat` runs
it as `[report]` at the end and the closing message points at it, instead of pointing at a
`.failures\` folder nobody opens.

Still open after this fix, and waiting on that file: `test_app_lifecycle`, `test_backup`,
`test_clone`, `test_docs`, `test_backends`. `test_backup` is the one to watch — it refuses a
copy when the destination is nearly full, so a report showing `free space: 0.4 GB` would
explain it, and the fix is disk, not code.

---

## The installer asked to download 1.9 GB and pressing Enter started it

`choice /c yn` reads a bare keypress and has no default, so the *first* letter was the answer
and there was no way to say "no, later" without knowing which letter that was. Both installers
now use `set /p`, print exactly what to type, and treat Enter as **no**:

```
  type y to install, or press Enter to skip:
```

Nothing about the downloads changed - XTTS-v2 is still ~1.9 GB, IndicF5 still needs the
licence click - but JARVIS runs without either of them. Piper (~60 MB, no account, no GPU)
speaks Tamil, Hindi and English, and a clone engine can be added later from Settings →
Voice. Answering no is "start using it today", not "skip setup".

---

## "clone voice la voice download aaga matiku" — it was never the internet

Four separate things could stop the clone engine before a byte arrived, and three of them
were ours. All four are fixed, and each one has a check named after the sentence it prevents
(`tests/test_engine_auto.py`).

**1. pip rejected the flag we added ourselves.** The installer ran

```
python -m pip install coqui-tts … --progress-bar ascii
```

pip 24 knew `ascii`; pip 26 offers `[auto, on, off, raw]` and **exits 2** before fetching
anything. The screen said only *"packages did not install (exit code 2)"* — which reads like
a network problem and is not. JARVIS now asks the pip that is actually installed which
spelling it accepts (`engines.bar_choice`, cached), and if it meets a pip newer than itself
it recognises `invalid choice` as our mistake and re-runs the same command once without the
flag. A modern pip's `Progress 512 of 4096` line is also understood, so the bar moves.

**2. A gated model ended the run instead of pausing it.** IndicF5 (Tamil, Hindi) is gated:
Hugging Face answers 401 until the licence is accepted once. The old flow downloaded
nothing, printed three instructions and told you to *"press Install again"*. Now the run
**pauses mid-download**, asks for the token in the same window (a paste box in
Settings → Voice, or `input()` in `install_clone.bat`), and continues in the same run. One
press, not two. Saying no is a decision, not a failure — the app keeps saying "system
voice" out loud, and Piper speaks English and Hindi today.

**3. There was no honest progress.** pip's and huggingface's bars are carriage-return, so a
pipe sees nothing for minutes and the screen looks frozen. `engines.read_progress()` turns
them into `12.5% · 238 MB of 1,900 MB · 3.1 MB/s · about 2:10 left`, and the .bat prints the
same numbers on one moving line.

**4. A full disk, said too late.** A 1.9 GB engine wants about 4.2 GB free, because pip
unpacks torch beside it. That is now checked **before** the download starts, with both
numbers in the message, so nothing is wasted.

**What to run**

```
install_clone.bat          Tamil clone (IndicF5, ~1.5 GB, free token needed once)
install_clone.bat en       English clone (XTTS-v2, ~1.9 GB, no account at all)
install_clone.bat hi       Hindi clone (IndicF5)
```

or, in the app: **Settings → Voice → "Download it for me — automatic"**. Both routes run the
same code (`tools/engine_get.py auto`, `engines.auto`), so the window and the terminal can
never disagree. Ctrl+C during the 6-second countdown stops it; running it again resumes,
because the packages and the weights are cached.

---

## "indicF5, xtts v2 also direct download aagum through terminal" — and they do

Correct, and measured again on 2026-10-25:

```
GET /api/models/coqui/XTTS-v2            200     gated: False   (public, no token)
GET /coqui/XTTS-v2/resolve/main/config.json   200
GET /api/models/ai4bharat/IndicF5        200     gated: "auto"
GET /ai4bharat/IndicF5/resolve/main/config.json  401  without a token
```

So XTTS-v2 needs no account at all, and IndicF5 is gated in the **easy** way: `auto` means
**any logged-in token is enough** — there is no approval to wait for. A terminal that has
ever run `huggingface-cli login` (or that sets `HF_TOKEN`) downloads both immediately, which
is why it worked there and not in the app. Three changes close that gap:

**1. JARVIS uses the token this computer already has.** `engines.token_source()` looks in
this order and reports which one it used:

| where | message |
|---|---|
| JARVIS settings (a token pasted in the app) | "saved in JARVIS settings" |
| `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` / `HUGGINGFACE_TOKEN` | "the HF_TOKEN in your terminal" |
| `huggingface_hub.get_token()` | "your huggingface-cli login" |
| `%USERPROFILE%\.cache\huggingface\token` | "your huggingface-cli login" |

The licence gate is asked with that token, so a machine that is already logged in never sees
a token prompt at all.

**2. A copy you already downloaded is used, not fetched twice.** `engines.local_copy()`
reads the same Hugging Face cache a terminal download fills
(`…\hub\models--coqui--XTTS-v2\snapshots\<sha>\…`) and treats a complete snapshot as
installed. `engine_get.py status` says so plainly:

```
  XTTS-v2 weights: already on this PC — …\models--coqui--XTTS-v2\snapshots\6c2b0d75…
```

**3. There is a direct download of its own.** Weights used to arrive only as a side effect of
`transformers`/`coqui-tts` "warming up"; when that library fails (hub version, a 401 worded as
`OSError`, a wheel newer than the code calling it) there was no download and no way to have
one. `engines.fetch()` is the terminal equivalent, in the app:

```
engine_get.py fetch xtts        # 9 files, 2,087 MB, straight over HTTPS
```

One GET per file, `Range` resume for anything that stopped, the same
`snapshots/<sha>/…` layout, progress in the same units as pip. Measured here: **2,087 MB
fetched, cancelled at 916 MB, resumed from 916 MB** without re-downloading a byte. It runs
automatically when a warm-up fails, so "the library could not do it" is no longer the end of
the story — and `--progress-bar` trouble, a missing wheel, or an offline minute are all
recoverable by running it again.

---

## `check.bat` on Windows: which of those red lines were the app, and which were the checker

A Windows run reported, among others:

```
FAIL  test_app_lifecycle   0.0s
FAIL  test_autostart_repair
FAIL  test_backup
FAIL  test_clone
FAIL  test_docs
FAIL  test_firstrun        it shut down cleanly when asked (exit 0) = 1
```

Three of those were the harness, not the app:

* **`test_firstrun` — "shut down cleanly" could never pass on Windows.** The check called
  `proc.terminate()`, which on Windows is `TerminateProcess`: exit code **1**, no shutdown,
  no farewell line. So the app was reported as failing to close cleanly when it had never
  been *asked* to close. It is now asked on the app's own lock socket (the same channel
  "bye jarvis" uses), which is what a person's Ctrl+Alt+Q does.
* **`test_autostart_repair` wrote the real `HKCU\…\Run` value.** To prove that a *stale*
  entry is repaired, the test has to write an entry — and on Windows that meant the machine
  running the tests would start JARVIS at the next login because a test ran. With
  `ARCDESK_AUTOSTART_FAKE=1` the entry is a small JSON file instead, so the whole repair
  story (off ⇒ no-op, healthy ⇒ fine, ghost path ⇒ repaired, off again ⇒ stays off) is
  proven without touching the laptop.
* **`test_docs` referenced a file that did not exist yet** in that build
  (`check-report.txt` was described before it was ever written). It is written now, by
  `tools/failure_report.py`, and the doc names the tool that writes it.

`test_app_lifecycle`, `test_backup`, `test_clone` and `test_engine_progress` still need a
real answer from a real Windows run, and the next run will give it in the same window:

```
[report] one file that says what failed and why ...
```

`tools/failure_report.py --write` prints the failing lines and copies them into
**check-report.txt** next to `check.bat` — platform, Python, folder, free space, one FAIL
line per broken check, and the last lines of the app's own log. Send that file instead of a
screenshot; it is small, and it contains no personal data beyond folder names. What it must
report is itself tested — `tests/test_failure_report.py` proves it quotes the real failing
lines, invents nothing when everything passed, and stays small enough to send.

The other half of the same report — the app booting fine while the tests went red — is what
these fixes were for. A green `BOOT · the window is shown` and three red test names is not a
contradiction: those tests measure the launcher, the autostart entry and the docs, and all
three had defects of their own.

---

## `install_clone.bat` printed forty lines of `transformers` internals and offered 1.9 GB

The screenshot (29.png) has three separate things in it, and only one was a bug in the app:

**1. "Access to model ai4bharat/IndicF5 is restricted… must be authenticated" — that is a
gated model, not a broken download.** IndicF5 (Tamil, Hindi) refuses every *file* until the
licence is accepted once, and the request carries a token. Measured on 2026-10-25:

```
GET /api/models/ai4bharat/IndicF5                    200     ← metadata is public
GET /ai4bharat/IndicF5/resolve/main/config.json      401     ← every FILE is not
GET /api/models/coqui/XTTS-v2                        200
GET /coqui/XTTS-v2/resolve/main/config.json          200     ← XTTS-v2 needs nothing
```

So the honest sentences are: **XTTS-v2 downloads with no account at all**, and **IndicF5 needs
a free token — and only IndicF5**. The app asks a real file URL for exactly this reason, tells
you before spending 200 MB on torch, and can use a token you already have:

| where the token can come from | what the app says |
|---|---|
| pasted in Settings → Voice | "saved in JARVIS settings" |
| `HF_TOKEN` in the environment | "the HF_TOKEN in your terminal" |
| `huggingface-cli login` token file | "your huggingface-cli login" |

**2. A traceback is not an error message.** The window filled with `File "…\transformers\…"`
lines and ended in `(IndicF5 download failed - retry with internet)`. Retrying would never
work: the licence is the blocker, not the connection. Every failure now ends in one sentence
that names the cause and the next click, and the raw output stays in the log.

**3. The order was wrong.** The gated 1.5 GB model was offered *first*, before the 1.9 GB one
that needs nothing. The order is now: **Piper (~60 MB, no account) → XTTS-v2 (English, no
account) → IndicF5 (Tamil/Hindi, token)**, and the batch file does the gated check *before*
anything is downloaded.

**Also worth knowing:** that copy was running from
`C:\Users\emera\Downloads\JARVIS-ready (1)\JARVIS`. The `(1)` means Explorer made a second
folder from the same zip, and Downloads is where cleaners work. Both `JARVIS.bat` and
`install_clone.bat` now say so at the top, and `ONE-PLACE.bat` moves the copy to
`%USERPROFILE%\JARVIS`. Keep one folder — two copies is how "it works, then it does not"
starts.

Every entry point now prints the build stamp first, so a screenshot can never again be from a
build two versions old:

```
0.1.0 · build 2026-10-25 · the one with the automatic voice download
```

---

## "task click pana process aaga matiku, appadiyae hang aagi nikkithu"

A click on a strand of the web did nothing that could be seen. Three separate reasons, all
fixed, each with a check in `tests/test_magic_click.py`:

**1. A working click and an ignored click looked the same.** The only feedback was a status
word at the bottom of a fullscreen picture. The deck now paints **open in a card in the
middle of the web** before it does anything, and takes the card away once the panel is
actually on screen.

**2. The in-JARVIS pages must open *inside* the deck.** FILES, NOTEPAD, CALC and TASK
MANAGER are strands that say `dock:` — the deck handles those itself, the panel appears over
the web, and nothing is launched behind it. TASK MANAGER reads the process table on a worker
with "reading the process list… (the deck stays usable)" on the panel, because
`psutil.process_iter` on a drawing thread is a frozen screen, not a slow one.

**3. A failure must leave a message.** Anything that lives on Windows (a browser, Windows
Settings) needs the deck to step aside — it is fullscreen and always-on-top, so the new
window would land behind it. When that launch fails, JARVIS now shows itself with the reason
and says Ctrl+Alt+J brings it back, and a **6-second watchdog** writes "it has not opened yet
— it is still trying" rather than leaving you to guess. Esc still leaves the deck from
anywhere.

## Start with the computer

`run.py` calls `autostart.repair()` and `autostart.ensure_first_time()` on every launch:

* first launch on this copy — **switched ON**, hidden (`pythonw run.py --shadow`), so the
  app is running in the background after a reboot with no window and no console;
* the folder moved or was re-unzipped — the entry points at a path that no longer exists,
  which *looks* registered and starts nothing; it is **repaired** to this folder and the
  console says so;
* switched off by you — **stays off**. Nothing turns itself back on.
* a portable copy (`ARCDESK_HOME` set) — never registered, because a startup entry pointing
  into a USB stick is a broken entry waiting to happen.

`AUTO-START.bat` does the same thing by hand, in one window, and prints what the system
reports afterwards.

---

## "conda create -n indicf5 … pip install git+…/IndicF5.git — ithu use panni IndicF5 download pannalaama?"

Yes. That env can run IndicF5, and JARVIS will **use it** instead of asking you to download
anything again. Three things are worth knowing before you start it, because two of them are
where people get stuck:

**1. `pip install git+https://github.com/ai4bharat/IndicF5.git` installs the CODE, not the
model.** Measured 2026-10-25: the repo has a setup.py (`name="f5_tts"`, version 0.1.0), so
the command really works — it gives you the `f5_tts` package and its requirements (torch,
transformers, accelerate…, `bitsandbytes` on Linux/Windows). It does **not** give you the
1.5 GB of weights. Those live at `ai4bharat/IndicF5` on Hugging Face, and that repo is
**gated**: every file answers 401 until a token is present.

**2. So log in once, in that same env** — one command, and it is the step that turns 401 into
a download:

```
conda activate indicf5
pip install -U huggingface_hub
huggingface-cli login           # paste a READ token from hf.co/settings/tokens
```

Then the weights arrive on first use, into `%USERPROFILE%\.cache\huggingface`:

```
pip install -U transformers soundfile
python -c "from transformers import AutoModel; AutoModel.from_pretrained('ai4bharat/IndicF5', trust_remote_code=True); print('weights ok')"
```

Accept the licence once on the model page first if the token still gets 401 — that page is
`huggingface.co/ai4bharat/IndicF5`, the free account clicks **Agree**, and after that any
token works (the repo is `gated: auto`, there is no approval queue).

**3. Put the env where JARVIS can see it — which it now can.** Before this change the app
only asked the interpreters it knew about, so an engine in a conda env was invisible and the
app said "not installed" to someone who had just installed it. `engines.conda_pythons()` now
looks in `CONDA_ENVS_PATH`, `CONDA_PREFIX`, and the usual `miniconda3\envs`,
`anaconda3\envs`, `miniforge3\envs`, `C:\ProgramData\miniconda3\envs`, `~/.conda/envs`,
`/opt/conda/envs`. Every candidate is **probed** for the engine's packages before it is
offered, so an empty env is never mistaken for a working one.

If your env lives somewhere unusual, point at it directly — an explicit choice is offered
first and wins:

```
set ARCDESK_ENGINE_PYTHON=C:\Users\you\miniconda3\envs\indicf5\python.exe
```

or in the app: **Settings → Voice → "Find what I installed"**. It prints every interpreter it
asked and what each one has, then a verdict — "Found it — … nothing needs downloading".

**How to tell it worked:** `python tools\engine_get.py status` says
`IndicF5 weights: already on this PC — …snapshots\…` and the Voice page stops saying "system
voice". Speaking takes a few seconds on a CPU; that is the model, not a bug.

---

## "through the terminal all engines downloaded machi but ipo kanom"

The engines were installed. The screen said **"Piper is not installed"** with a fresh
1.5 GB button. Nothing was lying about the disk — three separate things conspired, and all
three are fixed (checks in `tests/test_engine_found.py`):

**1. An engine is two halves, and only the whole thing was ever reported.** The *packages*
(conda env, venv, a terminal `pip install`) and the *weights* (`~/.cache/huggingface`, a
gated download that stopped at 401, or piper's separate `.onnx` voice files) were ANDed into
one "ready" flag. So "packages here, weights missing" arrived as the same words as "nothing
is installed", and the app offered to install what was already installed. `engines.status()`
now reports `ready`, `code` (packages), `local`/`model` (weights) and `python` (which
interpreter has them) separately, and the screen has a third state:

> **IndicF5 engine found — missing the IndicF5 weights.** Only that part is downloaded; the
> packages you installed are left exactly as they are.  `engine found: C:\…\envs\indicf5\python.exe`
> **\[Download only the missing part (1.5 GB)\]**

**2. `pip install piper-tts` was reported as "piper is not installed".** Piper's *engine* is a
pip package; its *voice* is a separate `.onnx` file per language (~60 MB). The old check
required both, so a complete engine install read as nothing. Now: engine found → "the piper
engine is installed — its voice files are not", with a **Download the voices only (~60 MB)**
button (`engines.missing_only("piper")` runs the voice fetcher, no pip, no venv).

**3. The search for "a python that already has this" finished after the screen was drawn, and
nothing re-read it.** The probe runs in the background on purpose (it starts child processes;
doing it on the drawing thread is what froze Settings). But the dialog read the answer once,
0 bits of it existed yet, and then sat there. It now watches
`engines.foreign_version()` every 1.5 s and repaints by itself when a probe answers.

**In a terminal, the same three fixes:**
```
python tools\engine_get.py status     # ready / engine found+what is missing / not installed
python tools\engine_get.py auto ta    # says "already ready, nothing to download" if it is
python tools\engine_get.py install indicf5   # finishes a half install, never a second one
```
And `install_clone.bat` now prints **[check] what this computer can speak with right now**
before it exits — the block that was missing when the question was "downloaded-a, aana
ready-a?".

**Conda specifically.** `engines.conda_pythons()` looks in `CONDA_ENVS_PATH`,
`CONDA_PREFIX`, `miniconda3\envs`, `anaconda3\envs`, `miniforge3\envs`,
`C:\ProgramData\miniconda3\envs`, `~/.conda\envs`, `/opt/conda/envs`, and every candidate
is probed for the engine's packages. An explicit choice wins and is offered first:
`set ARCDESK_ENGINE_PYTHON=C:\…\envs\indicf5\python.exe`.

---

## The Install button that did nothing (26.png, second report)

*"enakku ithula download aaga matiku and again antha circel desktop la vanthu hang aagi
stuck aaiduthu."* Two real bugs, both found by **pressing the button** instead of reading
the code — every earlier test built the dialog and never pressed Install, which is how 92
green checks shipped a dead button.

**1. The download could never start.** `_Worker.__init__` called
`make_fit(self, …)` — but `self` is a **QThread**, not a dialog, so `scroll_body()` asked it
for `.layout()` and raised:

```
AttributeError: '_Worker' object has no attribute 'layout'
```

That raise happened on the GUI thread, inside the button's slot, **after** the progress bar
was shown and Stop was enabled, and **before** `w.start()`. The screen therefore showed
exactly what 26.png shows — `installing IndicF5 · about 1500 MB…`, a 0 % bar, a live line
counting seconds, Stop enabled — with nothing behind it. `_begin` now reports any start
failure on screen ("the download could not even start (AttributeError: …)") and hands the
buttons back, so that half-busy state cannot exist any more.

**2. "Download it for me — automatic" raised `KeyError: 'id'`.** That button passes an
`engines.SPECS` entry to `_begin`, and SPECS entries have no `id` key (only the status rows
do). One press, one traceback, nothing on screen, window looks hung. Fixed to
`str(v.get("id") or engine)`.

**And three things that made a working download look hung:**

* **Stop did nothing while the child was silent.** `_run` read the pipe directly, so
  `read()` blocked until pip printed something; on a silent stage the button was pressed
  and the screen never changed. The pipe is now read on its own thread and the loop polls
  it every 250 ms, so Stop lands in well under a second (checked).
* **Silence was indistinguishable from a freeze.** After 25 quiet seconds the screen now
  says which stage it is on, how long it has been quiet, that the window is still
  answering, and that Stop / Esc work.
* **Closing the window mid-download destroyed a running QThread** (an abort, not an error),
  and the job kept writing files with nobody watching. Closing now stops and joins the
  worker first, and every finish clears a leftover wait-cursor (`uiwork.clear_stuck_cursors`)
  so the desktop ring cannot outlive the job that made it.

All of it is in `tests/test_engine_install_starts.py`: the press really starts a thread, the
thread really reaches the backend, a raise is reported, Stop works, and closing mid-download
ends the thread.

---

## "yethavathu select pana application crash aagi, close aaguthu"

A crash that closes the window leaves no Python traceback, so it was hunted by *pressing
things* rather than reading: every control in the app and in all five dialogs was driven in
its own process (77 actions), then every item of the quick menu (30 more). **No Python-level
crash** — the dialogs and the menus survive. That pointed at the one path that is not Python:
a **native library loaded inside the window's process**.

**The cause, and why it matches "select":** `clone._indicf5()` imported `transformers`,
`torch` and ran `AutoModel.from_pretrained(..., trust_remote_code=True)` **in the GUI
process**. That is ~1 GB of CUDA-linked DLLs loaded next to Qt's own, a repo's own code
executing inside the window, and a model load that freezes the drawing thread for tens of
seconds. On Windows a clashing DLL does not raise — it ends the process with no traceback.
Selecting the cloned voice (or letting JARVIS answer in it) is exactly what reaches that
path. The app already knew this for the installed `.exe` — that is the whole reason the
private engine folder exists — but a plain checkout that happened to have the packages
installed still took the in-process route.

**Fixed:** all clone speech goes through `_speak_in_a_child()`. The order is: the app's
private engine folder → an interpreter the person installed the engine into → **this same
interpreter, as a child process**. `_indicf5` / `_xtts` now refuse to run unless a human sets
`ARCDESK_ALLOW_INPROCESS_TTS=1`, and nothing sets it.

**And so a crash of any other kind is survivable:**

| before | now |
|---|---|
| a native crash left nothing to read | `%APPDATA%\ArcDesk\` + crash-report.txt — the log tail, `logs\fault.log` (faulthandler), and the session marker, written on the next start; `check.bat`'s report now includes it |
| two crashes in a row could leave the app unopenable | the next start **pauses the heavy visuals** (a GPU driver that dies on the deck crashes before the window is drawn), says so in the console, and changes none of your settings |
| "did it crash or did I close it?" | a clean close resets the counter; the console says `CRASH · …` with the file to send |

If it happens again: open `%APPDATA%\ArcDesk\` and send the crash-report.txt inside it. It has
no audio, no documents and no passwords in it — only log lines.

---

## "again ithu download aaga matiku … again antha circel vanthu hang aagi stuck aaiduthu"

Same words, third time — so this round was spent finding the reason a download can fail
**without an error message**, and the reason a half-finished one is thrown away.

**Bug found: piper's voices could never be downloaded. By anyone, on any machine.**
`_PIPER_WARM` (the script that fetches the `.onnx` voice files) did:

```python
out = target / name                      # a Path
with open(out + ".part", "wb") as f:     # TypeError: unsupported operand type(s) for +: 'PosixPath' and 'str'
```

Every language failed before a byte was kept, the script ended with
`no voice could be downloaded`, and the app could only say "Piper is not installed". Fixed
(`out.with_name(out.name + ".part")`, plus a size check before a file is kept). Verified:
`piper voices ready: 6 files` — en-GB, en-US and hi-IN, 63 MB each.

**A download no longer belongs to the window.** `arcdesk/engine_helper.py` starts
`tools/engine_get.py install <engine> --progress-file …` **detached** (`CREATE_NO_WINDOW |
DETACHED_PROCESS`, no console, not in the window's process group). The screen follows it by
reading a small JSON (0.1 ms a read, safe on the drawing thread) and Stop writes a stop file
the helper polls. Consequences, all checked in `tests/test_engine_background.py`:

* the download keeps going if the window freezes — the freeze no longer costs 1.5 GB;
* the download keeps going if the window is **closed**, which is what a person does when the
  screen stops moving (closing writes no stop request);
* the in-process thread is still there as a fallback (no Python on the machine, no tools
  folder), because a fallback that cannot start is not a fallback.

**And the freeze itself now has a name.** `uiwork.install()` — the 100 ms heartbeat that
logs `UI · the window was frozen for X s — main thread was in file:line` — was written and
**never called**. It is now installed at start-up, so the next hang writes the exact line
into the log, and the crash report (see the crash section above) carries it.

If it happens again: send `%APPDATA%\ArcDesk\` and the crash-report.txt in it. It names
the line, so the next fix is exact instead of a guess.

---

## "desktop shortcut um ila, proper ah open panra options um ila"

Opening JARVIS meant finding a file called `JARVIS.bat` and knowing why. Four things were
wrong, and all four are fixed:

| was | now |
|---|---|
| nothing ever created a shortcut (`install_shortcut.bat` existed; nobody ran it) | the **first launch** puts JARVIS on the Desktop and in the Start Menu, once, by itself |
| it pointed at `ArcDesk.exe` (a source copy has none) or `ArcDeskStart.bat` (a black console window for ever) | it runs `pythonw.exe run.py` — the window appears, no console |
| the icon lived in `shots/`, which is **never shipped**, so the shortcut got the Python icon | the icon ships in `assets/arc_icon.ico` |
| a moved folder left a shortcut that looked right and did nothing | it is **repaired** on the next launch, and **restored** once if it disappears |

**The rules, exactly** (`tools/shortcut.py` decides, `arcdesk/shortcut_offer.py` remembers):

* first launch on this copy → **create** (Desktop + Start Menu);
* the folder moved or was re-unzipped → **repair** — a shortcut pointing into a folder that
  no longer exists starts nothing, and that reads as "the app is broken";
* you deleted it → **restore once**, quietly, because "it disappeared" is the complaint;
* you unchecked it in **Settings → General → "Keep a JARVIS icon on my Desktop"** → it is
  removed and **never** recreated.

**If the icon ever goes missing**, double-click `CREATE-SHORTCUT.bat` in the JARVIS folder.
It is the same code, it prints where it put things, and running it twice is harmless.

**In a terminal:**
```
python tools\shortcut.py            # create or repair
python tools\shortcut.py --status   # what exists, and what it will run
python tools\shortcut.py --remove    # take it away
```

---

## The crash report, read out loud (2026-10-26)

The person sent the crash report. Every line of it is now a check in
`tests/test_engine_dialog_crash.py`, and two of the three were still live in the build they
were running:

**1. `TypeError: 'bool' object is not callable` — twice per refresh.**
`Check again` is a `QPushButton`; `clicked` emits `checked: bool`. It was connected straight
to `reload()`, so the refresh ran with `done_after=False` and then called it. Fixed twice
over: the signal now goes through a lambda, and `reload` only calls `done_after` when it is
`callable`.

**2. `QThread: Destroyed while thread '' is still running` — this is what closed the app.**
The download thread was created with the dialog as its parent (`_Worker(engine, self, …)`).
Destroying the dialog — closing Settings, quitting, anything the person does to a frozen
window — destroyed a **running** thread, and Qt treats that as fatal: no Python exception, no
traceback, `fault.log` empty. Exactly the report. Now:

* workers are **parentless** and held in `engine_dialog._LIVE_WORKERS`;
* destroying the dialog leaves a running download alone (it no longer belongs to the window);
* `app.aboutToQuit` calls `stop_all_workers()`: stop, wait 8 s, and only then — if a child
  process refuses to die — terminate it deliberately, so nothing can abort the shutdown.

**3. `the window was frozen for 0.5 s — main thread was in window.py:1834 in eventFilter`.**
That filter is installed on the *application*, so it sees every event of every widget. It now
asks two cheap questions first and hands everything else straight back to Qt.

**4. `Unable to set geometry 705x720 … Resulting 705x743`.**
The dialog asked for its content's `sizeHint`, which was taller than the work area of that
laptop screen. It now grows past the preferred size only when the widgets truly cannot
shrink, and its maximum is the work area — so every window fits, on every laptop.

**And one thing that is not a bug: two copies.** This log came from
`C:\Users\emera\Downloads\JARVIS-ready (12)\JARVIS`, while an older copy lived in
`C:\Users\emera\JARVIS`. Two copies means the fix you installed is not the one that runs.
Run `ONE-PLACE.bat` once, then always open the one in `%USERPROFILE%\JARVIS`.

**If the console said `SAFE · the last 2 runs ended unexpectedly …`,** that is the crash
safeguard working: after two unclean exits the next start pauses the heavy visuals so the
window is guaranteed to appear. Turn them back on in Settings once this build has run clean
once.

---

## "every option closes JARVIS" and "the MP3 reply voice says nothing"

Two separate faults, both answered with something that runs.

### 1. A window must not be able to end the app
`arcdesk/widgets/safeopen.py`. Every option in the app (`Settings`, the AI setup, the engines,
the ears, the voice library) now opens through `open_dialog()`. It builds and runs the dialog
inside a `try`, watches `sys.excepthook` **and** `threading.excepthook` for as long as the
dialog is up, writes the traceback to the log and to the crash bundle, and shows the person a
plain message — "JARVIS is still running … this was one window". A dialog that raises in its
constructor (which is what the crash report contained) leaves the app standing.

What it cannot do is survive a native abort — a segfault in a driver, a `QThread` destroyed
while it runs. Nothing in Python can. Those are why `tests/test_every_option.py --crashy`
exists: it runs each window in its own process, so an abort names the window instead of
killing the whole check.

### 2. An imported clip must be audible today
`arcdesk/voicematch.py`. The old chain was: clone engine (1.5–2.5 GB, torch, GPU) → piper →
the Windows voice. With no engine installed, an imported MP3 was **measured, stored, and never
used**, and the app said so only in small print. Now there is a step in between:

* the imported clip is analysed once — its pitch (Hz) and how much of it is speech;
* every sentence is rendered by whichever engine can speak that language, then **pitched onto
  the clip's own pitch** (overlap-add time stretch + resample, so the duration does not
  change), and played;
* it needs no download, no GPU, and no ffmpeg, and it is on by default (`ai.voice_match`).

It is a *match*, not a clone, and the app says so in those words. An exact clone still needs
the engine, which stays one button away in Settings → Voice.

### 3. Silence is no longer silent
`Voice.explain()` returns one sentence saying which voice will speak — "your clip, matched
voice · 118.4 Hz ta — no engine needed". Every skipped engine leaves its reason in
`voice.last_problems()`. **Settings → Voice → "Hear the reply voice now"** speaks one sentence
through the real chain and then prints what spoke, or why nothing came out. The Windows voice
is now tried three ways (SSML, then plain, then plain with no voice selected), because a
`<voice>` element naming a voice this PC does not have makes `SpeakSsml` throw — and the old
code threw that away along with stderr.

**If you hear nothing at all:** Windows Settings → System → Sound → make sure the right output
device is chosen and not muted, then press "Hear the reply voice now". Whatever it says is the
answer; the reason is written in the same sentence.

---

## The crash report from 26 October — what it actually said

The report arrived with the answer in it:

```
Windows fatal exception: code 0xc0000374          <- heap corruption
Current thread … settings.py in open_ears
CRITICAL qt  QThread: Destroyed while thread '' is still running
```

`0xc0000374` is not "an option crashed". It is a **use-after-free**: a `QThread` whose C++
object was destroyed while its thread was still running. PySide destroys that object the
moment Python garbage-collects the last reference — so **closing the Ears or Brain window
while a download ran** freed a running thread, and the abort then landed wherever the next
memory allocation happened to be. This time it was the next `open_ears`, which is why it
looked like every option took the app down.

Fixed with `arcdesk/widgets/qsafe.py`:

* download workers are **parentless** and owned by a module-level set, so no window's death
  can destroy a thread that is still running;
* `closeEvent` and `reject` on the Ears and Brain windows **stop the worker first**
  (cancel, wait a moment, move on — a worker that refuses to stop is left running and
  referenced, never killed; killing is the abort);
* `aboutToQuit` stops every remaining worker, so nothing writes files after the tray icon
  is gone;
* `tests/test_qsafe.py` closes the exact window at the exact moment and checks the app is
  standing afterwards.

Two accomplices were in the same report:

* **"Hear the reply voice now"** used to hop back to the GUI with `QTimer.singleShot`
  called from its worker thread — "Timers cannot be stopped from another thread" is in the
  log, and the answer sometimes never arrived. It is a signal now.
* `BrainDialog._Worker` called `make_fit` on **itself** (a QThread, not a window) before the
  thread ever started. It does not.

The `QWindowsWindow::setGeometry: Unable to set geometry …` lines that repeated through the
report are Qt clamping a dialog the person dragged near a screen edge — it fixes itself, so
that message is now demoted in the log. The next report will contain the fault, not six
copies of the noise around it.

---

## "Select a voice, press play, the app closes"

Two things were happening under that one sentence.

1. **A frozen window that looks like a dead one.** The voice library's *Hear* button
   called `clone.speak` on its own thread. The first sentence through a real engine means
   the child interpreter imports torch and loads a model — minutes — and for those minutes
   the window did not paint and Esc did not answer. It is in the voice library now: the
   button returns in milliseconds, the sentence is spoken on a worker, and the window
   stays alive to be seen (and to be Esc'd). `tests/test_voice_playback.py` proves it.

2. **An engine with no ceiling.** `sidecar_speak` waited on its child with no overall
   deadline. A hung engine meant a reply voice that never answered and a window that
   looked stopped. A 3-minute ceiling now: a late engine says so in words ("the engine
   took longer than 3 minutes to answer a sentence — it is not ready yet").

And the deeper fact, already fixed before this report and still worth knowing: **nothing
voice-related runs inside the window's process anymore.** The clone engine speaks in a
child interpreter, Piper in a child process, the Windows voice through a child
`powershell`. A crashing DLL now costs one sentence, not the window. If a voice attempt
still takes the app down on a machine, the app writes the crash report and the report says
where — send that file and the next answer is a line number, not a guess.

---

## The access violation in `eventFilter` (the 26 October report, second round)

The log's warning line is the confession:

```
WARNING qt  QWindowsContext::windowsProc: No Qt Window found for event 0x46 (…), hwnd=…
(a minute of it)
Windows fatal exception: access violation
  File "…/window.py", line 1853 in eventFilter
```

**Windows kept delivering window messages to a window Qt had already abandoned** — a C++
object destroyed, its native window still receiving traffic. The application-level event
filter was the first stop for every one of those messages, including ones whose pointer
was already freed — and a freed pointer is an access violation, not an exception.

Three doors now:

1. **The filter is on the window, not the application.** Qt forwards a widget's events to
   the filters of its ancestors, so this still sees the chat field, the dialogs and the
   quick menu — but it never sees events addressed to windows outside this tree, which
   is precisely where the dead ones live.
2. **`shiboken6.isValid` guards every object the filter touches** — the event, the modal
   widget, the focus widget, the focus widget's window. A deleted C++ object reads
   `False` and the answer to any event about it is simply "not me".
3. **The whole body is shielded**, including the final pass-through, so even a surprise
   from inside Qt comes out as "not handled", never as a dead process.

`tests/test_event_filter.py` reproduces the crash scenario in Python — a live event with
a deleted receiver, a deleted object behind the focus, a fabricated dead event — and
checks the filter's answer is always "not me" while JARVIS stays standing.
