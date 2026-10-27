"""Start JARVIS with Windows — from a double-click, with the folder written out.

    python tools/autostart_set.py status      what is registered right now
    python tools/autostart_set.py on          start with Windows, in the background
    python tools/autostart_set.py off         remove it
    python tools/autostart_set.py repair      fix an entry that points at a folder that moved

Why a tool and not a .bat with `reg add`: the registry line is easy to get wrong (a path
with a space, a relative path, the wrong hive), and "enabled" has to be proved by reading
it back. This is the same code the Settings checkbox and the boot-time self-repair use, so
all three can never disagree.

Nothing here needs admin: it is one value under HKEY_CURRENT_USER\\...\\Run, visible in
Task Manager → Startup apps, and `off` deletes exactly that one value.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _autostart():
    from arcdesk import autostart
    return autostart


def main(argv: list[str]) -> int:
    what = (argv[1] if len(argv) > 1 else "status").strip().lower()
    a = _autostart()

    if what == "status":
        state = a.status()
        print(f"  start with the computer : {'ON' if a.is_enabled() else 'off'}")
        if state.get("enabled"):
            print(f"  registered command      : {state.get('registered') or state.get('command')}")
            if state.get("stale"):
                print(f"  WARNING                 : that program is gone ({state.get('exe')})")
                print("                            run this file again with 'repair', or turn")
                print("                            it off and on to point it at this folder")
        if not state.get("supported"):
            print(f"  not available here      : {state.get('detail')}")
            return 1
        print(f"  it would start          : {a.folder()}")
        print("  how it starts           : hidden (no window, no console). Ctrl+Alt+J opens "
              "it, Ctrl+Alt+Q quits.")
        return 0

    if what == "on":
        got = a.enable()
        if not got.get("ok"):
            print(f"  could not register it: {got.get('error') or got}")
            return 1
        ok = a.is_enabled()
        print(f"  {'done' if ok else 'FAILED'} — start with the computer is "
              f"{'ON' if ok else 'still off'}")
        print(f"  it starts                : {a.folder()}")
        print("  hidden, so nothing pops up at login. Ctrl+Alt+J opens the window.")
        return 0 if ok else 1

    if what == "off":
        got = a.disable()
        print("  removed — JARVIS will not start by itself" if got.get("ok")
              else f"  could not remove it: {got.get('error') or got}")
        return 0 if got.get("ok") else 1

    if what == "repair":
        got = a.repair()
        if got.get("action") == "repaired":
            print(f"  repaired: {got.get('was')} -> {got.get('now')}")
            return 0
        if got.get("action") == "fine":
            print("  nothing to repair — it already points at this folder")
            return 0
        if got.get("action") == "off":
            print("  it is switched off, so there is nothing to repair. Use 'on' to turn "
                  "it on for this folder.")
            return 0
        print(f"  could not repair it ({got.get('error') or got.get('action')})")
        return 1

    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
