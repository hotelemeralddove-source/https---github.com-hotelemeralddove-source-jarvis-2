# Getting `ArcDeskSetup.exe` — the shortest path that works

The installer can only be built **on Windows**, because PyInstaller cannot cross-compile.
There are two ways to get one. Pick whichever you can do; both produce the same file.

---

## Way 1 — GitHub builds it for you (no Windows PC)

Roughly 10 minutes, and nothing to install.

### 1. Make an empty repo

<https://github.com/new> → name it `arcdesk` → **Private** is fine → do **not** add a
README (an empty repo is easier for the uploader) → **Create repository**.

### 2. Upload the source

**Easiest, no git needed:**

1. Unzip `arcdesk-src.zip` anywhere on your PC.
2. On the new repo's page click **uploading an existing file**
   (`https://github.com/<you>/arcdesk/upload/main`).
3. Drag **everything inside** the unzipped folder into the browser — including the
   `.github` folder. On Windows, hidden folders are still visible in Explorer if you turn
   on *View → Hidden items*; `.github` starts with a dot.
4. Commit message: `arcdesk`, then **Commit changes**.

**If you have git:**

```bat
cd arcdesk
git init
git add .
git commit -m "arcdesk"
git branch -M main
git remote add origin https://github.com/<you>/arcdesk.git
git push -u origin main
```

### 3. Wait for the build

The push starts **Actions → "build windows installer"** on its own. If you ever need to
start it by hand: **Actions → build windows installer → Run workflow**.

The job does, in order:

| step | what it proves |
|---|---|
| `python tests/run_all.py` | all **72 tests** pass — a failing test stops the build |
| `packaging\build_all.bat` | both executables + the installer are produced |
| `ArcDesk.exe --version` / `--doctor` | the **frozen** program actually starts and checks itself |
| SHA-256 of the installer | the file you download can be verified |

Green tick → continue. Red cross → open the failed step, copy the last 30 lines, and send
them; that log is the only thing needed to fix it.

### 4. Download it

**Actions → the green run → Artifacts → `ArcDeskSetup`** → a `.zip` containing:

```
ArcDeskSetup.exe      <- double-click this
SHA256SUMS.txt        <- optional: proves the file was not altered in transit
build_info.txt        <- which build this is
```

Unzip, double-click `ArcDeskSetup.exe`. Per-user install, **no admin prompt**, no Python,
no PATH editing.

---

## Way 2 — a Windows laptop

```bat
packaging\build_all.bat
```

One command. It installs what it needs (PySide6, vosk, sounddevice, sherpa-onnx,
PyInstaller, and Inno Setup if missing), runs the static pre-flight, builds both
executables, and compresses them into `dist\ArcDeskSetup.exe`.

Requirements: **Python 3.11+** (3.13 recommended) and an internet connection for the
first run. If Inno Setup is missing it says so and points at
`winget install JRSoftware.InnoSetup`.

---

## First launch, after installing

1. **"How should it open?"** — desktop icon, or start with Windows and listen for
   "hey jarvis". Both are pre-ticked; the second one is what makes the wake word work.
2. The installer offers **"Download the speech models now (70 MB)"** — leave it ticked.
   Without them "hey jarvis" cannot work, and the status line will say exactly that
   instead of failing silently.
3. **Settings → Voice → "Teach ARC my voice…"** — three takes of four seconds, then tick
   *"Only my voice may command ARC on this computer"*.
4. Proof, any time: `python tools\voice_setup.py selftest --against other.wav`, or
   **Settings → System → Run doctor**.

---

## What is still UNVERIFIED, stated plainly

| | why |
|---|---|
| the workflow itself has never run | it needs a GitHub repo and Actions minutes, which the machine that wrote it does not have |
| `ArcDeskSetup.exe` launching | needs Windows; only the Linux twin of the same spec was built and run here |
| Inno Setup producing the Setup | needs Inno Setup 6 on Windows |
| "hey jarvis" hearing your actual voice | needs a microphone and the speech model |

Everything else — 62 tests, 88 tools, the packaging pre-flight, the built bundle
(298.5 MB → 86.4 MB) — was executed, not assumed.
