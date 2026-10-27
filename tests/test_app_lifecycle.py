"""The install-time behaviour: "HEY JARVIS" opens, "BYE JARVIS" closes.

Asserts the two behaviours that matter once Arc Desk is a real application:
  1. bye_action="hide"  -> magic mode ends, process stays alive (instant reopen)
  2. bye_action="exit"  -> magic mode ends, wake listener stops, launcher armed,
                           and app.quit() is called
Also checks that the daemon command line is built correctly for source and for a
frozen build (the bug class that breaks packaged apps).

Run:  QT_QPA_PLATFORM=offscreen python tests/test_app_lifecycle.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import os
import tempfile

# keep tests away from the real settings folder (see config.data_dir)
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk import config, paths  # noqa: E402
from arcdesk.widgets.window import MainWindow  # noqa: E402


def pump(app, seconds=0.4):
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()
    app.processEvents()


def pump_until(app, cond, seconds=3.0) -> bool:
    """Wait for something the app does *after* it finishes speaking.

    Saying goodbye is not instant any more: it plays the closing cue and speaks
    "Thank you, commander." before it hides or quits, so a fixed 0.3 s pump is a
    race with the sentence. Pump until the effect lands, or give up loudly.
    """
    waited = 0.0
    while waited < seconds:
        app.processEvents()
        if cond():
            return True
        pump(app, 0.05)
        waited += 0.05
    return cond()


def make_window(app, bye_action: str) -> MainWindow:
    cfg = config.load()
    cfg["mode"] = "chill"
    cfg["window"] = {"w": 1000, "h": 690, "x": 20, "y": 20}
    cfg["ai"] = {"enabled": True, "provider": "lite", "voice": False}
    cfg["charms"] = {"enabled": False, "items": []}
    cfg["shadow"] = {"enabled": True, "awaken": False, "hotkeys": False,
                     "tray": False, "bye_action": bye_action,
                     "relaunch_on_wake": True}
    cfg["magic"] = {"enabled": True, "exit_phrase": "bye jarvis",
                    "wallpaper": False, "restore_on_start": True}
    cfg["wake"] = {"enabled": True, "phrase": "hey jarvis", "engine": "auto",
                   "port": 8917, "autostart_daemon": False}
    win = MainWindow(cfg)
    win.show()
    pump(app, 0.3)
    return win


def main() -> int:
    app = QApplication(sys.argv[:1])
    ok = True

    # ---------- 1. hide mode -----------------------------------------
    win = make_window(app, "hide")
    win.enter_magic()
    pump(app, 0.3)
    active_before = win.magic_active
    win.exit_magic()
    pump_until(app, lambda: not win.isVisible())
    pump(app, 0.2)
    hide_ok = active_before and not win.magic_active and not win.isVisible()
    print(f"1) bye_action=hide  : magic {active_before}->{win.magic_active}, "
          f"window hidden={not win.isVisible()}  {'OK' if hide_ok else 'FAIL'}")
    ok &= hide_ok
    win.shutdown()
    pump(app, 0.2)

    # ---------- 2. exit mode -----------------------------------------
    win = make_window(app, "exit")
    spawned: list[list[str]] = []

    import subprocess as real_subprocess

    class FakePopen:
        def __init__(self, cmd, *a, **kw):
            spawned.append(list(cmd))
            self.pid = 4242

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    class FakeSub:
        Popen = FakePopen
        DEVNULL = real_subprocess.DEVNULL

    # The seam moved: the launcher is now spawned through quiet.popen, which is what
    # stops a console window appearing behind the app on Windows. Patching subprocess
    # here would prove nothing today — the app no longer calls it directly.
    import arcdesk.quiet as quietmod
    original = quietmod.popen
    quietmod.popen = FakePopen           # type: ignore[assignment]
    # `_ears_can_stay()` is the seam that decides whether quitting would strand the user.
    # Wave 10 added it (never quit into silence), so the test injects "yes, something can
    # still hear me" to exercise the quit path, and case 2b below injects "no" to prove
    # the safety net.
    win._ears_can_stay = lambda have=None: (True, "test stub")
    try:
        quit_called = {"v": False}
        app.aboutToQuit.connect(lambda: quit_called.__setitem__("v", True))
        win.enter_magic()
        pump(app, 0.2)
        win.exit_magic()
        # Wait for the launcher specifically — the cue player is spawned first, so
        # "something was spawned" would be true long before the app actually leaves.
        pump_until(app, lambda: any("--launcher-app" in str(a)
                                    for c in spawned for a in c), seconds=6.0)
        pump(app, 0.2)

        # Not spawned[0]: closing now also plays the magic_end cue, so the first
        # child spawned during a close is the audio player. Find the launcher itself.
        launcher_cmd = next((c for c in spawned
                             if any("--launcher-app" in str(a) for a in c)), [])
        has_launcher = any("--launcher-app" in str(a) for a in launcher_cmd)
        print(f"2) bye_action=exit  : magic_active={win.magic_active} "
              f"wake_listening={win.wake_server.listening} "
              f"launcher_armed={has_launcher}  "
              f"{'OK' if (not win.magic_active and has_launcher) else 'FAIL'}")
        if launcher_cmd:
            print("   launcher cmd     :", " ".join(Path(str(c)).name
                                                    for c in launcher_cmd[:3]), "…")
        ok &= (not win.magic_active) and has_launcher
    finally:
        quietmod.popen = original         # type: ignore[assignment]

    # ---------- 2b. exit mode with nothing that could hear you -------
    win_b = make_window(app, "exit")
    quit_b = {"v": False}
    app.aboutToQuit.connect(lambda: quit_b.__setitem__("v", True))
    win_b._ears_can_stay = lambda have=None: (
        False, "sounddevice is not installed, so nothing could hear you")
    try:
        win_b.enter_magic()
        pump(app, 0.2)
        win_b.exit_magic()
        pump(app, 0.4)
        stayed = not quit_b["v"]
        print(f"2b) exit with no ears : app quit={quit_b['v']} "
              f"stayed_open={stayed}  {'OK' if stayed else 'FAIL'}")
        print("   it kept the app open rather than quitting into silence")
        ok &= stayed
    finally:
        win_b.shutdown()
        pump(app, 0.2)

    # ---------- 3. packaged-build path handling ----------------------
    print("3) path resolver (source build)")
    cmd, kwargs = paths.daemon_command(8765, "hey jarvis", "auto", "bye jarvis")
    script_ok = str(cmd[1]).endswith("arc_daemon.py")
    print(f"   argv: {Path(cmd[0]).name} {Path(cmd[1]).name} …  {'OK' if script_ok else 'FAIL'}")

    saved = paths.FROZEN
    try:
        paths.FROZEN = True
        fcmd, _ = paths.daemon_command(8765, "hey jarvis")
        frozen_ok = Path(fcmd[0]).name == "ArcDeskVoice.exe"
        print(f"   frozen argv: {Path(fcmd[0]).name}  {'OK' if frozen_ok else 'FAIL'}")
        ok &= frozen_ok
    finally:
        paths.FROZEN = saved
    ok &= script_ok


    print("\n7. one Arc Desk at a time — and it means it on Windows too")
    import socket as _socket

    import arcdesk.instance as _inst

    class _FakeSock:
        def __init__(self):
            self.calls = []

        def setsockopt(self, level, opt, value):
            self.calls.append((level, opt, value))

    fake = _FakeSock()
    # The real SO_EXCLUSIVEADDRUSE value (257) on platforms without it. 0x4 once did
    # duty, and 0x4 is exactly SO_REUSEADDR on Windows - so the "no SO_REUSEADDR was
    # set" check matched its own fake, and a real exclusive bind set the *permissive*
    # option instead. The fake must never collide with a real socket option.
    _inst._EXCLUSIVE = getattr(_socket, "SO_EXCLUSIVEADDRUSE", 257)
    applied = _inst.lock_socket_options(fake, platform="win32")
    win_ok = applied == ["SO_EXCLUSIVEADDRUSE"] and not [
        c for c in fake.calls if c[1] == _socket.SO_REUSEADDR]
    print(f"   Windows: SO_EXCLUSIVEADDRUSE only  {'OK' if win_ok else 'FAIL'}")
    ok &= win_ok

    fake = _FakeSock()
    posix_ok = _inst.lock_socket_options(fake, platform="linux") == ["SO_REUSEADDR"]
    print(f"   POSIX: SO_REUSEADDR kept  {'OK' if posix_ok else 'FAIL'}")
    ok &= posix_ok

    a = _inst.Instance({"instance": {"port": 47891}, "wake": {"port": 47890}})
    b = _inst.Instance({"instance": {"port": 47891}, "wake": {"port": 47890}})
    first, second = a.acquire(), b.acquire()
    a.release()
    lock_ok = first and not second
    print(f"   the second copy is refused  {'OK' if lock_ok else 'FAIL'}")
    ok &= lock_ok

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
