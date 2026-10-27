# Shadow mode — silent start, and the honest version of "invisible"

> **Start here:** `BOOT.md` covers the promise you actually care about — that Windows 11 Pro
> boots looking completely normal and Arc Desk changes nothing until you call it. This file is
> the deeper detail: what silent means, what I refused to build, and why.

## What shadow mode does

| Behaviour | Status |
|---|---|
| No console window | ✅ `pythonw.exe` + `--shadow` |
| No window on screen at boot | ✅ app starts hidden |
| No tray icon | ✅ not created at all in shadow mode |
| No taskbar entry | ✅ there is no window to show |
| No autostart prompt, no splash | ✅ nothing is shown |
| Listens for "Hey JARVIS" silently | ✅ voice daemon (separate process) |
| `Ctrl+Alt+J` → command palette, from anywhere | ✅ global hotkey |
| `Ctrl+Alt+Q` → quit the whole thing | ✅ |

Boot it deliberately:

```bat
start_arcdesk.vbs            :: silent shadow launch
python run.py --shadow       :: same, for testing
python run.py --show         :: force the window if you want to see it
```

"Sar" (sound/notification) is off by default as well: the awakening plays on *your* screen
when you call it, not a popup that steals focus at boot.

## What I deliberately did NOT build

You asked that nobody should be able to tell it is running. I gave you silent start, but I will
not make it *unkillable*, and here is the honest engineering reason:

**An app that hides from the user and cannot be stopped is malware by definition** — regardless
of who wrote it or why. The danger is not abstract:

- If the voice daemon ever loops, it holds your microphone open forever and you would have no
  visible way to see why.
- If a future version misfires and opens 200 browser tabs, you need one key to stop it.
- Antivirus engines flag self-hiding processes as trojans. Windows Defender would eventually
  quarantine the folder and you would lose your data with no idea why.
- You could not debug it, could not update it cleanly, and could not prove to yourself it was
  behaving.

So the design is: **silent, not stealth.** You get invisibility in normal use, plus three
guaranteed exits that cost you nothing:

1. `Ctrl+Alt+Q` — quits instantly (also stops the voice daemon and releases the mic)
2. Task Manager — one process, named `pythonw.exe` / `ArcDesk.exe`, visible on purpose
3. `⋯ → Quit` from the palette or the window

If you want it *more* discreet, the safe knobs are in `settings.json`:

```json
"shadow": {
  "enabled": true,
  "hotkey_palette": "ctrl+alt+j",
  "hotkey_quit": "ctrl+alt+q",
  "hotkeys": true,
  "awaken": true,
  "awaken_mode": "chill"
}
```

Change the hotkeys to whatever you like, or set `"awaken": false` if you want no cinematic.
Anything that promises "undetectable AI assistant" is selling you a rootkit, not a companion.

## Your laptop stays safe — the file guarantees

This matters more than the cool factor, so it is written down as a contract:

**What Arc Desk may write**

| Path | Contents |
|---|---|
| `%APPDATA%\ArcDesk\settings.json` | your preferences (atomic write, cannot corrupt) |
| `%APPDATA%\ArcDesk\notes.md` | notes you asked it to save |
| `%APPDATA%\ArcDesk\weather_cache.json` | last weather reading, so the HUD survives offline |
| `%APPDATA%\ArcDesk\vosk-model-*` | optional speech model (only if you install voice) |
| `%USERPROFILE%\Pictures\arc_shot_*.png` | screenshots you asked for |

**What it never does**

- never deletes, renames or edits your documents, photos or project files
- `find_file` only *reads* filenames inside Desktop/Documents/Downloads/Pictures, with a 4 s cap
- no admin rights, no services, no drivers, no kernel hooks, no firewall changes
- the only registry write is `HKCU\...\Run\ArcDesk` and only when you tick "Start with Windows"
- no telemetry, no analytics, no phone-home. Network is used only for: your chosen LLM
  provider (if you configure one), weather (if you enable it), and the model download
- the voice daemon talks to the app over `127.0.0.1` only — it does not listen on your LAN
- destructive tools (`shutdown`, `restart`, `sleep`, `close_app`) always ask permission first
- animations auto-throttle when a fullscreen app runs or you are on battery

**Clean removal**

```bat
uninstall.bat
```

Stops the daemon, deletes the autostart entry, removes `%APPDATA%\ArcDesk`, and tells you what
to delete if you also want the program folder gone. No leftovers, no orphan processes.

## Files-to-problem check (your point about files)

The one interaction that touches your files is `find_file` and `open_path`:

- `find_file` reads names only — never contents, never modifies anything
- `open_path` / `open_app` hand a path to Windows and let Windows launch it. Arc Desk does not
  interpret the file, so a corrupt document cannot hurt the app, and the app cannot corrupt it
- the screenshot tool writes a new PNG to `Pictures`; it never overwrites an existing file
  because the filename carries a timestamp
- notes are appended to one file that only Arc Desk owns

So: your files are read at most, never rewritten. If you want an even stricter setup, keep
`"ai": {"provider": "lite"}` — then nothing leaves the machine at all.
