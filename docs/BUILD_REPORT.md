# Build report — what was actually built, and what it broke

**Date:** 2026-10-23 · **Machine:** Linux x86_64, 2 cores, no audio device, no Windows
**Command:** `bash packaging/build_all.sh` (same spec, same pre-flight, same two executables as `packaging\build_all.bat`)

---

## 1. The honest headline

| | |
|---|---|
| `dist/ArcDesk/ArcDesk` (the window) | **built, and run** |
| `dist/ArcDesk/ArcDeskVoice` (the ears) | **built, and run** |
| The UI rendered from the frozen bundle | **yes** — `--screenshot`, 148 KB PNG, full HUD |
| `ArcDesk --doctor` inside the frozen app | **works** — 14 rows, `usable, with 1 warning` |
| `ArcDeskSetup.exe` (the Windows installer) | **not built here** — PyInstaller cannot cross-compile |

The `.exe` is not something this machine can produce, so it is not claimed. What this
machine *can* do — and did — is run the real build and prove the spec, the data files,
the hidden imports and both frozen entry points. That is where the bugs were.

---

## 2. Measured, not estimated

| | |
|---|---|
| PyInstaller, both executables, `--clean` | **51 s** |
| Whole build, one command, cold | **1 min 58 s** |
| Hidden imports collected | 94 |
| Data files | 4 (`KNOWS_PAGE`, `STUDIO_PAGE`, `TOOLS_PAGE`, `tools/doctor.py`) |
| Folder `dist/ArcDesk` | **298.5 MB** |
| Largest pieces | Qt 100 MB · sherpa-onnx 32 · libpython 28 · numpy 27 · Pillow 14 · lxml 9.4 |
| LZMA2 compressed (`dist/ArcDesk-linux.tar.xz`) | **86.4 MB — 29 % of the folder** |
| Static pre-flight | 72 checks, **0 failed**, 5 need a Windows machine |
| Test suite after every fix | **61/61 in 75 s** |
| Crosscheck (audited claims) | **54 proven · 0 failed** · 4 need Windows hardware |

---

## 3. Three bugs the tests could not see

Every one of these would have reached the user intact: the app imports fine, the tests
pass, the build either dies minutes later or ships something quietly dead.

### Bug 1 — the build did not start at all

`packaging/arcdesk.spec` applied `.parent` to `SPECPATH` **twice**:

```
ERROR: script '/home/user/run.py' not found
```

`SPECPATH` is already the folder holding the spec (`packaging/`), so the second `.parent`
walked one level *above* the repo. `build_all.bat` step 5 fails on this exactly the same
way on Windows — the earlier claim that the `.bat` worked had never been run.

**Fixed:** one `.parent`, plus a `SystemExit` that names `packaging/` and the two ways to
build, instead of a bare PyInstaller error.

### Bug 2 — `--doctor` died in the frozen app

```
ModuleNotFoundError: No module named 'doctor'
```

`tools/doctor.py` was never bundled, and `run.py` looked for it next to `__file__` (which
in a frozen build is inside `_internal`). `--doctor` is promised in README, INSTALL and
as a Settings button.

**Fixed:** the spec ships `tools/doctor.py` as data, and `run.py` resolves it from
`_MEIPASS`. Verified: 14 checks run from inside `dist/ArcDesk/ArcDesk`.

### Bug 3 — a build that would have killed the feature you just asked for

`sherpa-onnx` was **not** in `requirements-voice.txt`. A build made from the documented
requirements ships without the speaker-embedding engine — so Settings → Voice → *"Teach
ARC my voice"* answers "engine missing" on **every** machine, forever, because a frozen
EXE cannot pip install anything afterwards.

**Fixed:** it is in `requirements-voice.txt`, `build_all.bat` installs both requirement
files, and `tools/packaging.py` now **FAILS** the build if `vosk` or `sherpa_onnx` is not
importable at build time.

### Also fixed: a check that asserted nothing

`packaging.py` contained `if "startup" in iss: add("CHECKED", "installer: startup is
opt-in")` — a green row that verified a substring of a comment it had just matched. It now
parses the real `[Tasks]` block and the `Tasks:` gating on the shortcut and the startup
entry.

---

## 4. How the Windows installer gets made now

Two ways, neither of which puts anything on your laptop:

1. **A Windows PC** (yours, or any): `packaging\build_all.bat` → `dist\ArcDeskSetup.exe`
2. **No Windows PC**: `.github/workflows/build-windows.yml` — push the repo, then
   *Actions → "build windows installer" → Run workflow*, download the `ArcDeskSetup`
   artifact. The runner installs Python, the voice libraries, ffmpeg/node, PyInstaller and
   Inno Setup, runs all 61 tests, builds, and smoke-tests the frozen exe before uploading.

The workflow is written but **has not been run** — it needs a GitHub repo and Actions
minutes, which this sandbox has no access to. That is the one link in the chain still
unverified, and it is stated as unverified rather than assumed.

---

## 5. What is in the built folder

```
dist/ArcDesk/
  ArcDesk            7.7 MB   the window (frozen interpreter inside)
  ArcDeskVoice       9.5 MB   the ears — separate process, so a mic and a speech model
                              never share a process with the Qt window
  _internal/         283 MB   Qt, sherpa-onnx, vosk, numpy, Pillow, lxml,
                              the three generated HTML pages, tools/doctor.py
```

Two executables and a folder, not a one-file exe: one-file unpacks itself to `%TEMP%` on
every launch, which is slower every day you use it. `upx=False` on purpose — UPX is the
number-one cause of antivirus false positives on PyInstaller output.


---

## 6. Second audit (same day) — what the cross-check found

The user asked one sentence: *"is everything I asked for really there — Settings, the
metaphor, all the applications, everything enabled, all the files?"* That became
`tests/test_audit.py`, 60 measurements, and it found two more things that were quietly
not true:

| found | what it meant | fix |
|---|---|---|
| `config["effects"]` was **never read** by any code | you could set it in `settings.json` and nothing whatsoever would happen | `theme.tuned()` + `MainWindow.set_effects()` + **Settings → System → Visual effects** (follow / full / reduced / **off**); verified live: `chill` draws at 1.00, "off" at 0.00 and hides the charm overlay |
| backup's space guard reserved a flat 200 MB | a **400 KB** backup was refused with *"not enough room: 0.0 GB to copy, 0.2 GB free"* on a drive with 226 MB free | refuses only when the copy will not fit or would leave the drive nearly full; says **MB** when MB is the truth |

Both were live features, both were invisible to their own tests — the backup tests had
always run on a roomy disk, and no test had ever asked *"is this setting connected to
anything?"*. The rebuild after the fixes still produces a working bundle (298.5 MB →
86.4 MB, screenshot renders, `--doctor` green).
