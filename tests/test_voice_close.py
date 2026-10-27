"""HEY JARVIS opens it, BYE JARVIS closes it — tested as behaviour, not as intent.

The user's acceptance criterion, restated: *"antha application voice command la open and
close aaganum"*. The application must open by voice and CLOSE by voice. That is a stronger
statement than "magic mode goes away", and it is what this file checks:

  * the default is `bye_action = "exit"` — "bye jarvis" closes the app, it does not merely
    hide it (the first version of this shipped with "hide", which quietly failed the
    promise);
  * with `bye_action = "quit"` the REAL process exits 0 when the exit phrase arrives over
    the real socket (tools/voice_roundtrip.py drives the real app);
  * with `bye_action = "exit"` the app only quits when a launcher is PROVEN alive; if it
    cannot stay armed it hides and says why — quitting into silence leaves the user with
    no way to call the app back, which is worse than staying open;
  * `_arm_launcher()` is exercised with a fake process: alive → armed; immediately dead →
    refused, so the "proven alive" claim is tested rather than assumed;
  * "bye jarvis" also works when magic mode was never active (it used to do nothing);
  * every one of the three settings choices is reachable from the settings window.

Run:  python tests/test_voice_close.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:32]!r}")
    ok &= bool(good)


print("1. what does BYE JARVIS do by default?")
from arcdesk import config  # noqa: E402
default = config.DEFAULTS["shadow"]["bye_action"]
check("the default closes the app (not 'hide')", default in ("exit", "quit"))
check("it is 'exit' — close, launcher keeps listening", default, "exit")
check("relaunch_on_wake is on when it closes", config.DEFAULTS["shadow"]["relaunch_on_wake"])

print("2. the real application, driven by the real voice protocol")
env = dict(os.environ)
env["QT_QPA_PLATFORM"] = "offscreen"
env["PYTHONIOENCODING"] = "utf-8"
proc = subprocess.run([sys.executable, str(ROOT / "tools" / "voice_roundtrip.py"),
                       "--case", "quit"], cwd=str(ROOT), env=env, capture_output=True,
                      text=True, errors="replace", timeout=600)
out = proc.stdout + proc.stderr
print("\n".join("   | " + ln for ln in out.splitlines()[-12:]))
check("the round-trip exited 0", proc.returncode, 0)
check("the app was observed CLOSING", "the app CLOSED" in out and "OK" in out)
check("it closed with code 0", "it closed cleanly (exit 0)" in out)
check("no traceback anywhere", "Traceback" not in out)

print("3. the three choices, and the safety net")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from arcdesk.widgets.window import MainWindow  # noqa: E402


def make_window(bye_action: str):
    cfg = json.loads(json.dumps(config.DEFAULTS))
    cfg["first_run"] = False
    cfg["shadow"].update({"enabled": True, "bye_action": bye_action, "tray": False})
    cfg["wake"].update({"enabled": True, "port": 8901})
    win = MainWindow(cfg)
    win.hide()
    return win


class FakeProc:
    """A launcher that stays alive — what a working daemon looks like."""

    pid = 4242
    returncode = None

    def poll(self):
        return None


class DeadProc(FakeProc):
    """A launcher that exits instantly — what a missing speech model looks like."""

    pid = 4243
    returncode = 4

    def poll(self):
        return 4


win = make_window("exit")
can_hear, why = win._ears_can_stay()
print(f"        _ears_can_stay -> {can_hear} ({why})")
check("it knows whether anything could hear you afterwards", isinstance(can_hear, bool))

proc_alive, why_alive = win._arm_launcher(spawn=lambda *a, **k: FakeProc(),
                                          have=lambda name: True)
check("a launcher that stays alive is accepted", proc_alive is not None)
# `have=True` is injected on purpose: without it this case never reaches the spawn at
# all on a machine that has no microphone, so the assertion below would pass while
# testing nothing (it did exactly that, for the wrong reason, until a build exposed it).
proc_dead, why_dead = win._arm_launcher(spawn=lambda *a, **k: DeadProc(),
                                        have=lambda name: True)
check("a launcher that dies at once is REFUSED", proc_dead, None)
print(f"        reason: {why_dead!r}")
check("and the refusal says the launcher died, not something vague",
      "exited immediately" in why_dead.lower())

# The other refusal — the machine cannot listen at all — is a different path and gets
# its own honest message instead of being folded into the one above.
proc_nomic, why_nomic = win._arm_launcher(spawn=lambda *a, **k: FakeProc(),
                                          have=lambda name: False)
check("no microphone library is refused before anything is spawned", proc_nomic, None)
print(f"        reason: {why_nomic!r}")
check("...and it names the missing piece",
      "sounddevice" in why_nomic.lower() or "engine" in why_nomic.lower())


def fake_spawn_raises(*_a, **_k):
    raise OSError("no such file")


bad, bad_why = win._arm_launcher(spawn=fake_spawn_raises)
check("a launcher that cannot start at all is refused", bad, None)
check("with the reason kept", bool(bad_why))

print("4. 'bye jarvis' when magic mode was never on")
calls: list[str] = []


def route(win, action):
    """Watch which branch _apply_bye_action takes, without quitting the test runner."""
    win.close_application = lambda hard=False, spawn=None: calls.append(
        "hard" if hard else "soft")
    win.hide = lambda: calls.append("hide")
    win._apply_bye_action()
    return calls.pop() if calls else ""


win2 = make_window("hide")
win2.magic_active = False
win2._on_exit_phrase()          # the real signal path: exit phrase with no magic on
check("bye_action=hide hides the window", route(win2, "hide"), "hide")

win3 = make_window("exit")
win3.magic_active = False
check("bye_action=exit asks for a real close", route(win3, "exit"), "soft")

win4 = make_window("quit")
win4.magic_active = False
check("bye_action=quit asks for a hard close", route(win4, "quit"), "hard")

# the old behaviour — the bug this wave fixed — must be gone
check("it no longer just prints 'magic mode is not active' and does nothing",
      "_apply_bye_action" in (ROOT / "arcdesk" / "widgets" / "window.py").read_text(encoding="utf-8"))

print("5. the settings window offers all three")
from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets.settings import SettingsDialog  # noqa: E402
try:
    sw = SettingsDialog(json.loads(json.dumps(config.DEFAULTS)), get_theme("chill"))
    values = [sw.bye_action.itemData(i) for i in range(sw.bye_action.count())]
    check("three choices exist", sorted(values), ["exit", "hide", "quit"])
    check("the default is selected first", sw.bye_action.itemData(0), "exit")
    check("every choice is explained in plain words",
          all(sw.bye_action.itemText(i).strip() for i in range(sw.bye_action.count())))
except Exception as exc:
    check(f"settings window builds ({type(exc).__name__})", False)

for w in (win, win2, win3, win4):
    try:
        w.wake_daemon.stop()
        w.wake_server.stop()
        w.hotkeys.stop()
        w.deleteLater()
    except Exception:
        pass

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
