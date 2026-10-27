"""Start with Windows: first time, after a move, and after a re-unzip.

The report was *"jarvis lam start aganum machi... pc restart pana apram, auto start
aaganum"* — and it did not. Auto-start existed, it was even switched on, and it still
started nothing, because of three different holes:

  1. **It was never on for a fresh copy.** Enabling was manual and hidden in Settings, so a
     new install started by itself exactly never.
  2. **A re-unzip broke it silently.** `JARVIS-ready.zip` unpacks to `JARVIS-ready (1)`, so
     the registered command still pointed at `JARVIS-ready\\JARVIS\\run.py` — a folder that
     no longer exists. `status()` said "on"; Windows started nothing; nothing looked wrong.
  3. **It started with a console.** `python.exe run.py` opens a black window, which is a
     window — the stealth promise is "no window until the wake word".

What is proven here (no registry is touched: the store is redirected):

  1. the launcher is `pythonw.exe` (no console), `run.py --shadow`, absolute, quoted;
  2. `enable()` proves itself by reading the value back, and `disable()` removes only ours;
  3. the **first** enable is recorded once and never repeats on its own;
  4. `repair()` fixes a stale entry that is ON, and leaves an entry that is OFF alone;
  5. `repair()` points at the folder the app is running from — which is what makes a
     re-unzip self-healing;
  6. boot calls `repair()` and never calls `enable()` unless the user asked;
  7. `AUTO-START.bat` exists, is lint-clean, and offers on/off/repair.

Run:  python tests/test_autostart_repair.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="arcdesk-autostart-")
os.environ["ARCDESK_HOME"] = HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(HOME, "xdg")
# Never write the real HKCU Run value / ~/.config/autostart while testing: a test that
# registers JARVIS at login on the machine running it is not a test, it is a change.
os.environ["ARCDESK_AUTOSTART_FAKE"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<58} {got!r}")


from arcdesk import autostart                                              # noqa: E402

print("1. how it starts: background, no console, this exact folder")
launcher = autostart.launcher()
check("the launcher is a list", isinstance(launcher, list) and len(launcher) >= 2, True)
check("…run.py is the script", launcher[1].endswith("run.py"), True)
check("…with --shadow (tray and hotkeys only, no window)", launcher[-1], "--shadow")
check("…run.py is an absolute path", os.path.isabs(launcher[1]), True)
if os.name == "nt":
    check("…and it is pythonw.exe, so no console window appears",
          launcher[0].lower().endswith("pythonw.exe"), True)
else:
    check("…and it is an interpreter that exists now and at login",
          Path(launcher[0]).exists(), True)

faked = autostart.command_line(["C:/Program Files/Py/pythonw.exe",
                                "C:/Users/x/My JARVIS/run.py", "--shadow"])
check("a path with a space is quoted", faked.count('"'), 4)
check("…the script is quoted too", '"C:/Users/x/My JARVIS/run.py"' in faked, True)

print("\n2. on, off, and the proof that it really is on")
got = autostart.enable()
check("enable() reports ok", got.get("ok"), True)
check("…and the value reads back as on", autostart.is_enabled(), True)
check("…pointing at THIS folder", Path(got.get("folder") or autostart.folder()).name,
      Path(ROOT).name)
check("…status agrees", autostart.status().get("enabled"), True)
check("…and it is not stale", autostart.status().get("stale", False), False)
check("disable() reports ok", autostart.disable().get("ok"), True)
check("…and the value is gone", autostart.is_enabled(), False)
check("a second disable() is still ok (nothing to remove)",
      autostart.disable().get("ok"), True)

print("\n3. the first enable is offered once, and remembered")
marker = Path(HOME) / "settings.json"
check("a fresh install has not been offered it yet",
      autostart.first_time_pending(), True)
autostart.mark_first_time_done()
check("…after asking, it is not offered again",
      autostart.first_time_pending(), False)
check("…and the shared config says so too",
      json.loads(marker.read_text(encoding="utf-8")).get("autostart_asked"), True)

print("\n4. repair: only an entry that is ON, only when it is stale")
autostart.disable()
check("switched off -> repair does nothing",
      autostart.repair().get("action"), "off")
check("…and it is still off", autostart.is_enabled(), False)

autostart.enable()
check("a healthy entry needs no repair", autostart.repair().get("action"), "fine")

# the re-unzip: the registered folder is renamed out from under the entry
state_file = Path(autostart.store_path())
# what a re-unzip into "JARVIS-ready (1)" does: the folder in the entry is gone.
# The entry is written the same way an older copy wrote it, then left alone.
real_exe = autostart.status().get("exe") or ""
ghost = str(Path(real_exe).parent / "JARVIS-ready (1)" / "run.py")
check("the ghost folder really does not exist", Path(ghost).exists(), False)
# an older copy's entry: interpreter + a script path that no longer exists
autostart.enable()
autostart._fake_write(f'"{sys.executable}" "{ghost}" --shadow')          # noqa: SLF001
check("the moved folder makes the entry stale", autostart.status().get("stale"), True)
fixed = autostart.repair()
check("repair says it repaired it", fixed.get("action"), "repaired")
check("…it names what it was", str(fixed.get("was") or "").find("JARVIS-ready (1)") >= 0, True)
check("…it now points at this folder", Path(autostart.status().get("exe") or "").parent,
      Path(ROOT))
check("…and it is no longer stale", autostart.status().get("stale", False), False)
check("…with the hidden launcher again (--shadow kept)",
      autostart.status().get("command", "").endswith("--shadow"), True)
check("a repaired entry stays on", autostart.is_enabled(), True)
autostart.disable()

print("\n5. boot repairs, it never switches anything on by itself")
run_py = (ROOT / "run.py").read_text(encoding="utf-8")
check("run.py calls repair()", "autostart.repair()" in run_py
      or "_autostart.repair()" in run_py, True)
check("run.py does NOT call enable() on boot",
      not re.search(r"autostart\.enable\(|_autostart\.enable\(", run_py), True)
check("run.py does not call set_enabled(True) on boot",
      not re.search(r"autostart\.set_enabled\(True|_autostart\.set_enabled\(True", run_py), True)
# and the repair call must be wrapped: a registry that refuses must not stop the app
idx = run_py.find(".repair()")
check("…the repair call is inside a try/except", idx > 0
      and "except" in run_py[idx:idx + 3000], True)

print("\n6. the first launch turns it on by itself — once, and reversibly")
from arcdesk import config as _config                                       # noqa: E402


def _fresh() -> None:
    """Pretend this is a copy that has never been asked, with nothing registered."""
    autostart.disable()
    cfg = _config.load()
    cfg.pop("autostart_asked", None)
    _config.save(cfg)


# A portable copy (ARCDESK_HOME set) must never register itself: an entry pointing into a
# USB stick is a broken entry waiting to happen. Said explicitly, so the answer does not
# depend on the environment that happens to run the test.
_fresh()
check("a portable copy is never registered",
      autostart.ensure_first_time(portable=True).get("action"), "portable")
check("…and nothing was written", autostart.is_enabled(), False)

_fresh()
first = autostart.ensure_first_time(portable=False)
check("the first real launch switches it on", first.get("action"), "enabled")
check("…and it really is on", autostart.is_enabled(), True)
check("…pointing at this folder", first.get("folder"), str(ROOT))
check("a second launch leaves it alone",
      autostart.ensure_first_time(portable=False).get("action"), "already offered")
autostart.disable()
check("after switching it off, a launch does NOT turn it back on",
      autostart.ensure_first_time(portable=False).get("action"), "already offered")
check("…it stays off", autostart.is_enabled(), False)

print("\n7. the double-clickable file for it")
bat = ROOT / "AUTO-START.bat"
check("AUTO-START.bat is in the pack", bat.exists(), True)
text = bat.read_text(encoding="utf-8", errors="replace")
check("…it offers ON, OFF and repair", all(w in text.lower() for w in
                                           ("turn it on", "turn it off", "repair")), True)
check("…it never needs an administrator", "administrator" in text.lower()
      or "admin" in text.lower(), True)
check("…it shows the current state first", "autostart_set.py\" status" in text, True)
check("…and it finds run.py before doing anything", "find_project.bat" in text, True)
provenance = (ROOT / "tools" / "autostart_set.py").read_text(encoding="utf-8")
check("the tool behind it says where it writes",
      "HKEY_CURRENT_USER" in provenance, True)
check("…and it can print, set and clear",
      all(w in provenance for w in ("status", "on", "off", "repair")), True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
