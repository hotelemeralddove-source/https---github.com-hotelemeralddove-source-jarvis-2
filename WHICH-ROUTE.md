# ONE route. This is the answer to "which one do I use?"

You have been switching between two ways of running JARVIS, and that is where the
confusion came from — not from the app.

| | **Route A — the folder you have** | Route B — the installed `ArcDesk.exe` |
|---|---|---|
| what it is | `JARVIS.bat` inside the project folder | a packaged Windows program |
| who it is for | **you**, on this laptop | handing it to someone who has no Python |
| updates | **one file**: `UPDATE-JARVIS.bat` | new `.exe`, reinstall |
| speed | starts in ~2 s after the first run | starts a little faster |
| if it breaks | the error is on screen, in English | an installer problem, no console to read |
| needs | the folder + `.venv` (built once) | nothing |

## Use Route A. Delete the confusion, not the app.

```
Desktop\JARVIS\                 <- keep this single folder, it IS the app
    JARVIS.bat                  <- double-click this to start it
    UPDATE-JARVIS.bat           <- double-click this to update it
    JARVIS-DIAGNOSE.bat         <- only if it ever looks dead
    check.bat                   <- the doctor, when you want proof
    run.py, arcdesk\, tools\, requirements.txt, .venv\
```

**Start:** `JARVIS.bat` → it runs in the background, no window, until "hey jarvis" or
Ctrl+Alt+J. Ctrl+Alt+Q quits.

**Update:** download **one** file — `ArcDesk-full-project.zip` (or a fix pack — both work
now) — leave it in Downloads, and
double-click `UPDATE-JARVIS.bat`. Inside, it calls the app's own Python
(`tools\update_from_zip.py`) so it cannot be stopped by a PowerShell type error; if you
ever prefer to skip the `.bat`, that script is the whole updater:

```
.venv\Scripts\python.exe tools\update_from_zip.py --check   (say what it would do)
.venv\Scripts\python.exe tools\update_from_zip.py           (do it)
``` It finds the zip, checks it is really the app (a fix pack
has no `run.py` and is refused), copies it over this folder **without touching `.venv`**,
installs any new library, and starts JARVIS again. No unzipping by hand, no five downloads,
no `install_voice.bat`, no `install_clone.bat`.

## The things you should stop doing (each one caused a "stop or error")

| don't | because |
|---|---|
| unzip a **fix pack** on its own | it is a handful of files, not the app → "Could not open requirements file" |
| run `install.bat` in a folder with no `run.py` | there is nothing to install there (it now says so in plain words) |
| run `install_voice.bat` / `install_clone.bat` | the same jobs are one click in **Settings → Voice** |
| copy `.venv` to another PC | it contains absolute paths; `JARVIS.bat` builds its own |
| keep two copies and open both | the second one says "already running" on purpose |

## When you want the `.exe` instead

Only for giving JARVIS to someone who will not have Python. Then use the **installer**
(`ArcDeskSetup.exe`) or the portable zip from the GitHub Actions artifacts — one file, it
carries Python inside. Do not mix the two on the same laptop: they keep separate settings.

## If `check.bat` shows failures

`check.bat` is a doctor, not the app. It runs nine sections and now ends with a count:

```
=====================
3 of 9 sections reported a problem.
  1. read the FIRST failing line - the rest is usually noise
  2. the per-test details of section 3 are in the folder  .failures\
  3. send me the failing block (a screenshot is enough)
=====================
```

The 78 individual tests are on `arcdesk`'s own record — they pass here on Linux. Where they
failed on a Windows laptop, the cause was the *test harness*, not your app, and each one is
fixed:

| failing test | what it was | fixed by |
|---|---|---|
| `test_backup` | it created a symlink, which Windows refuses without admin | the symlink part is skipped when the OS will not allow one |
| `test_clean` | it demanded ffmpeg — which this app does not need any more | becomes a SKIP, with the reason printed |
| `test_clone` | an assertion about the old "ffmpeg is needed" wording, and it started a real pip install | updated to the new decoder behaviour; tests never install |
| `test_engines` | hard-coded `/tmp/...` paths, which do not exist on Windows | a real temporary folder |
| step 1/9 of `check.bat` | `os.killpg` — **does not exist on Windows** | one `_stop_child()` helper that uses `terminate()` there |
| `test_app_lifecycle` | not reproduced here; the failing line is printed, see below | — |

If `test_app_lifecycle` is the one still failing on your laptop, I need one line from it:
run `check.bat`, then open the failure file that `check.bat` names (one per test, in the .failures folder) and send the line that starts
with `FAIL`. That is enough to fix it without guessing.
