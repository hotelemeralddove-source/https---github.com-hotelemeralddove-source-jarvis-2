# Normal boot — your Windows 11 Pro stays exactly as it is

This is the promise, written so it can be checked:

> **Boot your laptop and Windows 11 Pro looks 100 % normal.** Wallpaper, desktop icons,
> Recycle Bin, taskbar, Start menu, Explorer, every feature — untouched. Arc Desk waits in the
> background. Only when you say **"Hey JARVIS"** does anything happen, and it lasts ~1.9
> seconds before handing the screen back to you.

## What boot looks like

| | |
|---|---|
| Wallpaper | unchanged — we never call any wallpaper API |
| Desktop icons / Recycle Bin | unchanged — we never hide or rearrange icons |
| Taskbar | unchanged — no always-on-top strip, no docking, no autohide tricks |
| Start menu / Explorer | unchanged — we never touch or restart Explorer |
| Theme / accent colour | unchanged — our dark theme is *inside our window only* |
| Screen at boot | **nothing from Arc Desk.** No splash, no popup, no window |
| Tray | one icon (like Dropbox, Steam, OneDrive). Turn it off with `"tray": false` |
| CPU at idle | ~1.6 % of one core, and it drops to ~0 when nothing is animating |

## What happens on "Hey JARVIS"

```
mic hears "hey jarvis"
      ↓  (daemon, separate process)
app receives wake signal
      ↓
full-screen cinematic ~1.9 s  (rings, scan lines, "ARC // ONLINE")
      ↓  screen returns to you
Arc Desk window appears with the console open, ready for the command
```

That cinematic is the only time Arc Desk covers your screen, it is click-through, Esc cancels
it, and it deletes itself afterwards.

## How to check that your Windows really is untouched

**In the app:** `⋯ → Check: is my Windows untouched?`

**From a terminal:**

```bat
python tools\desktop_check.py --save     :: take a baseline (do this first)
python tools\desktop_check.py            :: compare any time later
python tools\desktop_check.py --scan     :: scan the source for desktop-altering APIs
```

The first run saves a baseline of: wallpaper path, wallpaper style, screensaver, current theme,
taskbar autohide state, whether Explorer is running, and how many items are on your desktop.
Every later run diffs against it and prints `UNTOUCHED` or names exactly what changed.

The `--scan` mode greps Arc Desk's own source for the APIs apps use to mess with a shell —
`SPI_SETDESKWALLPAPER`, `SPI_SETICONS`, `Shell_TrayWnd`, `taskkill explorer`,
`reg add ... Explorer`, hidden-icon flags, `SetWindowDisplayAffinity`. Current result:

```
source scan (desktop-altering APIs):
  clean — no wallpaper/taskbar/explorer/icon APIs anywhere in the code.
RESULT: CLEAN
```

That list is in `arcdesk/desktop_guard.py`. If a future feature ever needs one of those calls,
the scan fails and the feature gets rejected in review. That is the point of a contract:
it should be uncomfortable to break.

## Where Arc Desk is allowed to write

| Path | Why |
|---|---|
| `%APPDATA%\ArcDesk\settings.json` | your preferences (atomic write) |
| `%APPDATA%\ArcDesk\notes.md` | notes you asked for |
| `%APPDATA%\ArcDesk\weather_cache.json` | last weather reading |
| `%APPDATA%\ArcDesk\desktop_baseline.json` | the audit snapshot above |
| `%APPDATA%\ArcDesk\vosk-model-*` | speech model, only if you install voice |
| `%USERPROFILE%\Pictures\arc_shot_*.png` | screenshots you asked for |
| `HKCU\...\Run\ArcDesk` | **only** if you tick "Start with Windows" |

Nothing else. No system folders, no Program Files writes, no services, no drivers, no firewall
or Defender changes, no admin prompts.

## "But I don't want to see it running at all"

Two honest options:

1. **Tray off** — `"shadow": {"tray": false}`. Then at boot there is no window, no icon, no
   taskbar entry. `Ctrl+Alt+J` still opens the palette and `Ctrl+Alt+Q` still quits.
2. **Tray on (default)** — one icon you can right-click: *Show · Awaken · Command palette ·
   Check Windows untouched · Quit*. This is what I recommend, because it is the difference
   between "a background app" and "a background app nobody can see".

I will not build option 3 ("invisible even in Task Manager, no kill switch"). That is the
definition of malware, and it is the fastest way to get your folder quarantined by Defender
with no recovery path. Silent is a feature; undetectable is a bug.

## Uninstall

```bat
uninstall.bat
```

Stops the app and the voice daemon, removes the autostart key, deletes `%APPDATA%\ArcDesk`.
Then delete the folder. Windows is left exactly as it was before you ever installed this.
