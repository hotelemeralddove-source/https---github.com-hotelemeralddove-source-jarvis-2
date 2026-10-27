# Magic mode — "Hey JARVIS" in, "BYE JARVIS" out

## The honest answer to your question first

> *"Windows 11 Pro original OS and laptop-ku any issues varuma?"*

**Depends entirely on how "total change" is implemented.** There are two versions, and they are
not equally safe:

| What people usually mean by "total change" | Risk | Do we do it? |
|---|---|---|
| Swap the desktop wallpaper | none — one reversible API call, we keep the old path | ✅ yes |
| Cover the taskbar with a fullscreen topmost window | none — we never touch the taskbar itself | ✅ yes |
| Our own fullscreen ARC workspace | none — it is just an app window | ✅ yes |
| **Replace Explorer as the shell** (`Shell=` registry / kill `explorer.exe`) | **real** — Start menu, taskbar, file dialogs and notifications break; if the app crashes you get a black screen; breaks on Windows updates; antivirus flags it | ❌ **never** |

So: **the visible effect is the same, the risk is not.** We fake the takeover with a window we
control, so your actual Windows session is never in a modified state.

## Entering and leaving

```
"Hey JARVIS"                        "BYE JARVIS"
     ↓                                   ↓
cinematic (1.9 s)                   wallpaper restored
     ↓                                   ↓
fullscreen ARC workspace            overlay + charms back
+ wallpaper swapped                 app hides, Windows normal
+ journal written                   journal deleted
```

Exiting also works with **Esc**, **`⋯ → Magic mode`** (untick), **`Ctrl+Alt+Q`**, or by typing
`exit` / `back to normal` in the magic screen's command line.

## The journal — why a crash cannot leave you stuck

Magic mode changes something real (the wallpaper), so it is treated like a transaction:

1. Before touching anything we write `%APPDATA%\ArcDesk\magic_journal.json` containing the
   **original** wallpaper path and the fact that a session is active.
2. On a clean exit: wallpaper restored → journal deleted.
3. On `Ctrl+Alt+Q`, close, or quit: the exit path runs the same restore.
4. **On a hard kill (Task Manager / power loss):** the journal survives. The next time Arc Desk
   starts, `restore_if_needed()` reads it and puts your wallpaper back automatically, then says
   so in the console.

Verified by `tests/test_magic.py`:

```
daemon (wake) : simulated wake + command: open google
magic active  : True        journal while active: True
daemon (exit) : simulated exit phrase: bye jarvis
magic active  : False       journal left: False
stale journal healed: cleared a stale magic session | journal now: False
PASS
```

It also covers the edge case I got wrong the first time: saying **"bye jarvis" during the 1.9 s
cinematic** now cancels it instead of being swallowed and letting magic mode open a second later.

## What is on the magic screen

- Fullscreen reactor with the clock inside it
- Six app tiles: Files, Notepad, Calc, Task Manager, Settings, Browser
- One command line: type or speak — same 88 tools as always
- `SAY "BYE JARVIS" · ESC · BACK TO NORMAL WINDOWS` always visible

## Settings that control it

`⋯ → Settings… → System`

| Setting | Default | Meaning |
|---|---|---|
| `"Hey JARVIS" enters magic mode` | on | off = the small window opens instead |
| Exit phrase | `bye jarvis` | anything you like — same phrase engine as the wake word |
| Swap the wallpaper | on | off = visual takeover only, zero OS changes |

## When the wallpaper is *not* touched

Set `"magic": {"wallpaper": false}` and magic mode becomes 100 % app-side: cover the screen,
show ARC, leave every Windows setting alone. That is the version to use if you want zero
footprint at all — and it still looks identical on screen.

## Audit trail

`python tools/desktop_check.py --scan` still passes, because the wallpaper call is **whitelisted
by filename** (`magic.py`) and reported instead of hidden:

```
audited exceptions:
  changes the wallpaper — allowed only in magic.py (journal + auto-restore)
  writes desktop settings — allowed only in magic.py (journal + auto-restore)
```

Any *other* file using those APIs still fails the scan. `explorer.exe` killing, `Shell=` registry
writes, icon hiding and taskbar manipulation remain forbidden everywhere, with no exceptions.
