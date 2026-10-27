"""A JARVIS that opens from an icon — not from a .bat file you have to remember

    python tests/test_shortcut.py

The report: *"desktop shortcut um ila, proper ah open panra options um ila … everytime
jarvis.bat ah double click pani open panra mathiri iruku"*. The old `install_shortcut.bat`
had three faults and one of them was fatal:

  * it pointed at `ArcDesk.exe` (a plain checkout does not have one) or `ArcDeskStart.bat`,
    which keeps a black console window open for ever;
  * its icon lived in `shots/`, which is **not shipped** with a release, so the shortcut
    fell back to the Python icon and looked like a script;
  * nothing ever ran it.

Checked here, without Windows and without touching the real Desktop:

  1. the launch spec: a source copy runs `pythonw` (no console) with `run.py`, an installed
     app runs its own `.exe`, and the arguments are quoted so a path with spaces works;
  2. the icon ships (`assets/`, not `shots/`), so the shortcut has a real picture;
  3. both destinations - Desktop and Start Menu - and the right extension per OS;
  4. the decision: create on the first launch, repair when the folder moved, restore once
     if it disappeared, never argue if it was switched off;
  5. the switches: the checkbox removes it, CREATE-SHORTCUT.bat rebuilds it, and the app's
     start-up calls it (a fault there must never stop the window).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_OFFLINE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-shortcut-")
os.environ["ARCDESK_NO_FOREIGN_PYTHON"] = "1"
DESK = Path(tempfile.mkdtemp(prefix="arcdesk-desktop-"))
os.environ["ARCDESK_DESKTOP"] = str(DESK)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<58} {str(got)[:46]!r}")
    if not same:
        print(f"        expected {want!r}")


import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("shortcut_tool", ROOT / "tools" / "shortcut.py")
tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(tool)

print("\n1. what a click runs")
launch = tool.launch()
check("a source copy runs a python", launch["kind"] in ("python", "bat"), True)
check("…this interpreter when there is no venv", launch["target"],
      str(Path(sys.executable).with_name("pythonw.exe")) if os.name == "nt"
      else sys.executable)
check("…and it is given run.py, quoted for a path with spaces",
      launch["args"], f'"{ROOT / "run.py"}"')
check("…with the project as the working folder", launch["working"], str(ROOT))
check("…and no --shadow: a click should SHOW the window", "--shadow" in launch["args"], False)

fake_exe = ROOT / "ArcDesk.exe"
try:
    fake_exe.write_bytes(b"MZ")
    packed = tool.launch()
    check("an installed .exe is used directly", packed["kind"], "exe")
    check("…with --show", packed["args"], "--show")
finally:
    try:
        fake_exe.unlink()
    except OSError:
        pass

print("\n2. the icon actually ships")
icon = tool.icon_path()
check("there is an .ico", icon.is_file(), True)
check("…and it is NOT in shots/ (that folder is never released)",
      str(icon.parent.name), "assets")
check("…and it is a real icon, not a 0-byte placeholder", icon.stat().st_size > 10_000, True)

print("\n3. both places a person looks")
where = tool.destinations()
check("a Desktop shortcut", str(where["desktop"]).endswith(
    "JARVIS.lnk" if os.name == "nt" else "JARVIS.desktop"), True)
check("…in the Desktop folder", Path(where["desktop"]).parent, DESK)
check("a Start Menu entry", "Start Menu/Programs" in str(where["menu"]).replace("\\", "/")
      if os.name == "nt" else "applications" in str(where["menu"]), True)
made = tool.create()
check("creating it works", made["ok"], True)
check("…both of them", len(made["made"]), 2)
check("…pointing at this folder", made["working"] if "working" in made else str(ROOT),
      str(ROOT))
if os.name != "nt":
    text = Path(where["desktop"]).read_text(encoding="utf-8")
    check("it is marked as not-a-terminal (no black window)", "Terminal=false" in text, True)
    check("…and it carries the icon", str(icon) in text, True)
    check("…and it runs the app, not the .bat", str(where["desktop"]) and "run.py" in text, True)
check("status now says both exist", (tool.status()["desktop"], tool.status()["menu"]),
      (True, True))

print("\n4. when to make it, in one table")
from arcdesk import shortcut_offer  # noqa: E402

here = str(ROOT)
check("first launch, nothing known -> create", shortcut_offer.decide({}, {"desktop": False}), "create")
check("shortcut there, same folder -> nothing to do",
      shortcut_offer.decide({"made": True, "folder": here}, {"desktop": True, "folder": here}),
      "none")
check("shortcut there, folder moved -> repair",
      shortcut_offer.decide({"made": True, "folder": "C:/old/JARVIS"},
                            {"desktop": True, "folder": here}), "repair")
check("deleted after it was made -> restore",
      shortcut_offer.decide({"made": True, "folder": here},
                            {"desktop": False, "folder": here}), "restore")
check("switched off in Settings -> never touched",
      shortcut_offer.decide({"made": True, "folder": here, "off": True},
                            {"desktop": False, "folder": here}), "none")

print("\n5. the switch, and the wiring")
state = shortcut_offer.state_path()
got = shortcut_offer.ensure()
check("ensure() acts on the decision", got["action"] in ("create", "repair", "restore"), True)
check("…and records what it did", json.loads(state.read_text(encoding="utf-8"))["made"], True)
off = shortcut_offer.set_preference(False)
check("switching it off removes the files", off["action"], "removed")
check("…the Desktop one is gone", Path(where["desktop"]).exists(), False)
check("…and it stays off next launch",
      shortcut_offer.decide(json.loads(state.read_text(encoding="utf-8")),
                            {"desktop": False, "folder": here}), "none")
back = shortcut_offer.set_preference(True)
check("switching it back on recreates it", Path(where["desktop"]).exists(), True)

run_src = (ROOT / "run.py").read_text(encoding="utf-8")
check("the app's start-up makes the shortcut", "shortcut_offer as _shortcuts" in run_src, True)
check("…and a failure there cannot stop the window",
      "the shortcut check did not run" in run_src, True)
bat = (ROOT / "CREATE-SHORTCUT.bat").read_text(encoding="ascii")
check("CREATE-SHORTCUT.bat exists for the bad days", "tools\\shortcut.py" in bat, True)
check("…and it finds the project first", "find_project.bat" in bat, True)
jarvis = (ROOT / "JARVIS.bat").read_bytes().decode("ascii")
check("JARVIS.bat also makes the icon once the app is up", "tools\\shortcut.py" in jarvis, True)
settings = (ROOT / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
check("Settings has the one checkbox", "Keep a JARVIS icon on my Desktop" in settings, True)
check("…and it acts immediately, not at the next launch",
      "shortcut_offer.set_preference(want_icon)" in settings, True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
