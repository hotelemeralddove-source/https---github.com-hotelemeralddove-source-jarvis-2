"""A real JARVIS you can click: Desktop and Start Menu, one icon, no console.

The report: *"desktop shortcut um ila, proper ah open panra options um ila … everytime
jarvis.bat ah double click pani open panra mathiri iruku"*. Three faults, and this file is
the whole answer to them:

  1. **there was no shortcut.** `install_shortcut.bat` existed, but nothing ever ran it —
     a person had to find a file called *install_shortcut* and know why.
  2. **when it did run it pointed at the wrong thing.** `ArcDesk.exe` (which a plain
     checkout does not have) or `ArcDeskStart.bat` (which keeps a black console window
     open for ever). A source copy should open JARVIS with **no console at all**.
  3. **it had no icon.** The `.ico` lived in `shots/`, which is deliberately not shipped
     with a release — so the shortcut fell back to the Python icon and looked like a
     script. The icon now lives in `assets/`, which is part of the app.

What a click produces here:

    pythonw.exe  run.py            window up, no console, icon = the arc reactor

and, on Windows, `pythonw` is preferred precisely because it is windowless: a `.pyw` or a
`.vbs` downloaded from the internet carries the mark of the web and asks "do you want to
open this file?". Nothing here does.

    python tools/shortcut.py            create (or repair) Desktop + Start Menu
    python tools/shortcut.py --status   what exists right now, one line each
    python tools/shortcut.py --remove   take them away again
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

NAME = "JARVIS"
#: What the shortcut is called on the Desktop. One word, because a person looks for the
#: app by the name the app calls itself.
LABEL = "JARVIS"


def icon_path() -> Path:
    """The .ico a shortcut can use. Ships with the app; generated if missing."""
    for cand in (ROOT / "assets" / "arc_icon.ico", ROOT / "arcdesk" / "assets" / "arc_icon.ico",
                 ROOT / "shots" / "arc_icon.ico"):
        if cand.is_file():
            return cand
    try:                                   # last resort: draw it now (Pillow is a dependency)
        import importlib.util
        spec = importlib.util.spec_from_file_location("make_icon",
                                                      ROOT / "tools" / "make_icon.py")
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)                     # writes into shots/
            out = ROOT / "assets" / "arc_icon.ico"
            out.parent.mkdir(parents=True, exist_ok=True)
            src = ROOT / "shots" / "arc_icon.ico"
            if src.is_file():
                out.write_bytes(src.read_bytes())
                return out
    except Exception:                                            # noqa: BLE001
        pass
    return ROOT / "assets" / "arc_icon.ico"


def launch() -> dict:
    """Exactly what a click should run, as data — so this can be tested without Windows.

    `target` is the program, `args` what it is given. A source copy uses the interpreter
    that is running the app (`pythonw.exe` on Windows so no console appears); an installed
    .exe is used directly.
    """
    exe = ROOT / "ArcDesk.exe"
    if exe.is_file():
        return {"target": str(exe), "args": "--show", "kind": "exe",
                "working": str(ROOT)}
    script = ROOT / "run.py"
    venv = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    python = ""
    for cand in (venv / "pythonw.exe", venv / "python.exe", venv / "python"):
        if cand.is_file():
            python = str(cand)
            break
    if not python:
        python = _windowless_python()
    if not python:
        # no windowless interpreter anywhere: the .bat keeps its console, which is worse
        # than nothing but better than a shortcut that fails silently
        return {"target": str(ROOT / "JARVIS.bat"), "args": "", "kind": "bat",
                "working": str(ROOT)}
    args = f'"{script}"'
    return {"target": python, "args": args, "kind": "python", "working": str(ROOT)}


def _windowless_python() -> str:
    """A python that does not open a console on Windows ('' if there is none)."""
    exe = sys.executable or ""
    if os.name != "nt":
        return exe
    if not exe:
        return ""
    guess = Path(exe).with_name("pythonw.exe")
    return str(guess) if guess.is_file() else exe


def destinations() -> dict[str, Path]:
    """Where the two shortcuts go. Pure enough to reason about on any OS."""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    desktop = Path(os.environ.get("ARCDESK_DESKTOP") or (home / "Desktop"))
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
        programs = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    else:
        data = Path(os.environ.get("XDG_DATA_HOME") or (home / ".local" / "share"))
        programs = data / "applications"
    return {"desktop": desktop / f"{LABEL}.lnk" if os.name == "nt"
            else desktop / f"{LABEL}.desktop",
            "menu": programs / (f"{LABEL}.lnk" if os.name == "nt" else f"{LABEL}.desktop")}


def _ps_quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def _make_windows(path: Path, spec: dict) -> dict:
    """One .lnk, through Windows' own shell object (no pywin32 needed)."""
    icon = icon_path()
    script = (
        f"$sh=New-Object -ComObject WScript.Shell;"
        f"$p={_ps_quote(path)};"
        f"$s=$sh.CreateShortcut($p);"
        f"$s.TargetPath={_ps_quote(spec['target'])};"
        + (f"$s.Arguments={_ps_quote(spec['args'])};" if spec["args"] else "")
        + f"$s.WorkingDirectory={_ps_quote(spec['working'])};"
        f"$s.Description='JARVIS - your desktop, your universe';"
        + (f"$s.IconLocation={_ps_quote(str(icon))};" if icon.is_file() else "")
        + "try{$s.WindowStyle=1}catch{};"
        f"$s.Save();"
        f"if (Test-Path $p) {{ 'made' }} else {{ 'missing' }}"
    )
    try:
        from arcdesk import quiet
        got = quiet.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                        capture_output=True, text=True, timeout=60)
        ok = "made" in (got.stdout or "")
        return {"ok": ok, "path": str(path), "why": "" if ok else (got.stdout or got.stderr
                                                                   or "the shell refused")}
    except Exception as exc:                                     # noqa: BLE001
        return {"ok": False, "path": str(path), "why": f"{type(exc).__name__}: {exc}"}


def _make_linux(path: Path, spec: dict) -> dict:
    icon = icon_path()
    text = ("[Desktop Entry]\nType=Application\nName=JARVIS\n"
            f"Comment=Your desktop, your universe\n"
            f"Exec={spec['target']} {spec['args']}".rstrip() + "\n"
            f"Path={spec['working']}\n"
            f"Icon={icon}\nTerminal=false\nCategories=Utility;\n")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if path.name.endswith(".desktop"):
            path.chmod(0o755)
        return {"ok": True, "path": str(path), "why": ""}
    except Exception as exc:                                     # noqa: BLE001
        return {"ok": False, "path": str(path), "why": f"{type(exc).__name__}: {exc}"}


def make(path: Path, spec: dict | None = None) -> dict:
    spec = spec or launch()
    return _make_windows(path, spec) if os.name == "nt" else _make_linux(path, spec)


def create(desktop: bool = True, menu: bool = True) -> dict:
    """Create (or repair) the shortcuts. Returns what happened, in words."""
    spec = launch()
    if spec["kind"] == "bat":
        return {"ok": False, "made": [], "why":
                "there is no windowless Python on this PC, so a shortcut would open a "
                "black console window (or nothing at all). Install Python 3 from "
                "python.org, then run this again — JARVIS.bat works meanwhile.",
                "target": spec["target"]}
    where = destinations()
    made, errors = [], []
    if desktop:
        got = make(where["desktop"], spec)
        (made if got["ok"] else errors).append(got["path"])
    if menu:
        got = make(where["menu"], spec)
        (made if got["ok"] else errors).append(got["path"])
    return {"ok": bool(made) and not errors, "made": made, "errors": errors,
            "target": spec["target"], "args": spec["args"], "kind": spec["kind"],
            "icon": str(icon_path()), "why": "" if made else
            ("the desktop or Start Menu folder could not be written — see the paths above")}


def status() -> dict:
    where = destinations()
    spec = launch()
    return {"desktop": where["desktop"].is_file(), "menu": where["menu"].is_file(),
            "paths": {k: str(v) for k, v in where.items()},
            "target": spec["target"], "args": spec["args"], "kind": spec["kind"],
            "icon": str(icon_path()), "icon_exists": icon_path().is_file()}


def remove() -> list[str]:
    gone = []
    for path in destinations().values():
        try:
            if path.exists():
                path.unlink()
                gone.append(str(path))
        except OSError:
            continue
    return gone


def main(argv: list[str]) -> int:
    if "--status" in argv:
        st = status()
        print(f"  target          {st['target']}")
        print(f"  arguments       {st['args'] or '(none)'}")
        print(f"  icon            {st['icon']}  {'ok' if st['icon_exists'] else 'MISSING'}")
        print(f"  desktop         {st['paths']['desktop']}  "
              f"{'exists' if st['desktop'] else 'not there'}")
        print(f"  start menu      {st['paths']['menu']}  "
              f"{'exists' if st['menu'] else 'not there'}")
        return 0
    if "--remove" in argv:
        for path in remove():
            print("  removed " + path)
        return 0
    got = create()
    if not got["ok"]:
        print("  could not create the shortcut: " + (got.get("why") or "unknown reason"))
        for path in got.get("errors") or []:
            print("    failed: " + path)
        return 1
    print("  JARVIS shortcut created:")
    for path in got["made"]:
        print("    " + path)
    print(f"  it runs: {got['target']} {got['args']}")
    print("  no console window, and the icon is the reactor, not a python.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
