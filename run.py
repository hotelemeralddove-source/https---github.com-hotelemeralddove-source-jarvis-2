"""Arc Desk launcher.

    python run.py                      # normal boot
    python run.py --mode gaming        # boot straight into a mode
    python run.py --screenshot out.png # render a still (dev/QA helper)
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon

from arcdesk import __version__, config, logs
from arcdesk.theme import MODE_ORDER
from arcdesk.widgets.window import MainWindow

def _port_live(port: int, timeout: float = 1.0) -> bool:
    """Does anything still answer on the lock port (a socket thread can outlive
    a frozen GUI — that is exactly the case this exists for)."""
    try:
        import socket as _sk
        with _sk.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _holder_pid(port: int, _text: str | None = None) -> int:
    """The pid owning the LISTEN socket on `port`, straight from the OS (0 if none).

    In a frozen build the holder's command line is `ArcDesk.exe`, not `run.py`,
    so no process scan can find it — but the lock port names it exactly.
    `_text` takes the netstat output in (tests); on Windows we fetch it live.
    """
    try:
        if sys.platform == "win32" and _text is None:
            import subprocess as _sp
            _text = _sp.run(["netstat", "-ano"], capture_output=True,
                            text=True, timeout=10).stdout
        for row in (_text or "").splitlines():
            parts = row.split()
            if (len(parts) >= 5 and parts[0].startswith("TCP")
                    and parts[1].endswith(":%d" % port) and parts[3] == "LISTENING"):
                return int(parts[4])
    except Exception:                                            # noqa: BLE001
        pass
    return 0


def _record_stop(pid: int) -> None:
    """Same marker tools/jarvis_state.py writes: the next start explains a stop
    we performed as an expected action, not as a crash."""
    try:
        import datetime as _dt
        import json as _json
        import time as _time
        marker = logs.log_path().parent / "launcher-stop.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        data = {"pids": [], "ts": _time.time(),
                "at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        if marker.exists():
            try:
                old = _json.loads(marker.read_text(encoding="utf-8") or "{}")
                if _time.time() - float(old.get("ts", 0)) <= 600:
                    data["pids"] = [x for x in old.get("pids", []) if int(x) != int(pid)]
                    data["ts"] = float(old["ts"])
            except Exception:                                    # noqa: BLE001
                pass
        data["pids"].append(int(pid))
        marker.write_text(_json.dumps(data), encoding="utf-8")
    except Exception:                                            # noqa: BLE001
        pass


def main(argv: list[str] | None = None) -> int:
    # First, before a single print(): a windowless launch (pythonw.exe, the Startup
    # shortcut, the installed exe) has sys.stdout = None, and the first print would
    # otherwise kill the app with nothing on screen to explain it.
    logs.ensure_streams()
    argv = list(sys.argv if argv is None else argv)
    ap = argparse.ArgumentParser(prog="arcdesk", description="Arc Desk — Phase 1")
    ap.add_argument("--mode", choices=MODE_ORDER, help="start in this power mode")
    ap.add_argument("--screenshot", metavar="PNG", help="save a still frame and exit")
    ap.add_argument("--advance", type=float, default=2.6, help="seconds to fast-forward")
    ap.add_argument("--no-tray", action="store_true")
    ap.add_argument("--console", action="store_true", help="open the JARVIS console")
    ap.add_argument("--download-voice-model", dest="download_voice_model",
                    action="store_true",
                    help="download the speech model (40 MB) and the speaker model (30 MB), "
                         "then exit — the installer offers this")
    ap.add_argument("--ask", metavar="TEXT", help="send one prompt and print JARVIS's answer")
    ap.add_argument("--demo-chat", action="store_true", help="seed a sample conversation")
    ap.add_argument("--shadow", action="store_true",
                    help="start hidden: no window, no tray icon (boot with Windows)")
    ap.add_argument("--show", action="store_true", help="force the window visible")
    ap.add_argument("--palette", action="store_true", help="open the command palette")
    ap.add_argument("--awaken-shot", metavar="PNG",
                    help="render the awakening animation mid-frame and exit")
    ap.add_argument("--palette-shot", metavar="PNG", help="render the palette and exit")
    ap.add_argument("--magic-shot", metavar="PNG",
                    help="render the magic-mode screen and exit")
    ap.add_argument("--charms-shot", metavar="PNG",
                    help="render the charm overlay over a mock desktop and exit")
    ap.add_argument("--doctor", action="store_true",
                    help="check this install and exit (python run.py --doctor)")
    ap.add_argument("--no-instance", action="store_true",
                    help="allow a second copy (dev/screenshot runs)")
    ap.add_argument("--version", action="version", version=f"Arc Desk {__version__}")
    args, qt_args = ap.parse_known_args(argv[1:])

    logs.install()
    # Native aborts (an import pulling a clashing DLL) skip every Python handler; this is
    # the only thing that records them. And if the LAST run left its marker behind, say so
    # — "the app closed by itself" needs a reason on screen, not a shrug.
    logs.watch_crashes()
    # The freeze detector: a 100 ms heartbeat on the drawing thread. If the window ever
    # stops answering, the log gets the exact file and line it was stuck in — that is the
    # difference between "antha circel vanthu hang aagi stuck aaiduthu" and a name.
    try:
        from arcdesk import uiwork as _uiwork
        _uiwork.install()
    except Exception:                                            # noqa: BLE001
        pass
    _unclean = logs.begin_session()

    def _finish(code: int) -> int:
        """One-shot modes (--doctor, --screenshot, --ask…) end properly, so the next real
        launch does not announce "last time it did not close" about a screenshot."""
        logs.end_session()
        return code


    if args.doctor:
        # In a frozen build __file__ points into the temp/install internals, so the
        # tools folder has to be found from the bundle root (PyInstaller's _MEIPASS).
        base = Path(getattr(sys, "_MEIPASS", "") or Path(__file__).resolve().parent)
        # Loaded by file path, NOT by putting tools/ on sys.path: that folder contains
        # tools/packaging.py, which would then shadow the pip package `packaging` for
        # everything imported afterwards. That is exactly how the GitHub build broke.
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("_arc_doctor", base / "tools" / "doctor.py")
        doctor = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(doctor)            # type: ignore[union-attr]
        return doctor.run()

    # Bundled tools (ffmpeg, node) live inside the install. Adding them to THIS process's
    # PATH is what removes the "set your path" step for the user — and it touches nothing
    # outside this process, so uninstalling leaves Windows exactly as it was.
    from arcdesk import paths as _paths
    _runtime = _paths.activate_runtime()
    if _runtime:
        # say it once, in the log, so "is ffmpeg included?" has an answer that is not a guess
        print("bundled runtime on PATH: " + ", ".join(_runtime), flush=True)

    cfg = config.load()
    # A fresh install writes its settings file immediately. It used to appear only when
    # something else happened to call save() — which, with the floating charms on by
    # default, was "always". Turning those off exposed it: the first boot left no
    # settings file at all, so nothing the person chose could be shown to persist.
    if not config.settings_path().exists():
        config.save(cfg)
    if args.mode:
        cfg["mode"] = args.mode
    if args.shadow:
        # This launch only. It used to be written into the settings file, so ONE boot
        # with Windows (which passes --shadow) turned every later double-click into a
        # hidden process: installed, and apparently dead. The Run key passes --shadow
        # every boot, so nothing is lost by keeping it out of the saved settings
        # (config.save strips the underscore keys).
        cfg["_stealth_this_launch"] = True
    if args.show:
        cfg["_force_show"] = True

    # One Arc Desk at a time. A second launch does not open a second reactor —
    # it tells the first one to wake up, which is what the user expects from
    # saying "Hey Jarvis" twice.
    dev_run = bool(args.screenshot or args.ask or args.demo_chat or args.palette_shot
                   or args.magic_shot or args.awaken_shot or args.charms_shot)
    inst = None
    if not (args.no_instance or dev_run):
        from arcdesk.instance import Instance
        inst = Instance(cfg)
        if not inst.acquire():
            # The lock port is taken. That means a copy is already up — but saying so and
            # exiting leaves the person with NO window, which is the report: "app open
            # aagala". So the second copy ASKS the first one to show itself, and only
            # then goes away.
            from arcdesk.instance import wake_now
            port = inst.port
            inst = None
            # Ask, and wait for the answer. A write that nobody acted on is not success:
            # that is how the launcher came to print "brought it to the front" over an
            # empty desktop. `wake_now` retries for ~1.5 s because a wake that lands
            # while the first copy is still building its window is dropped.
            got = wake_now(cfg)
            if got.get("ack"):
                print("JARVIS is already running — asked it to come to the front.")
                logs.note(f"BOOT · port {port} is held by a running JARVIS; it answered the "
                          f"wake (handled={bool(got.get('handled'))}), nothing else to start")
                return _finish(0)
            # Bound but silent: a stuck copy, or a socket left behind. Say it out loud
            # *and* exit with a code the launcher can act on (3 = "held but dead"), so it
            # can close just that copy and start a fresh one instead of leaving the person
            # with a friendly sentence and no window.
            # Held but silent: a stuck copy owns the lock — a "Not Responding"
            # window whose socket thread still answers. In the .bat world the
            # .bat acted on this; a frozen ArcDesk.exe has no .bat, so the app
            # does the launcher's own job: close that holder by its port, and
            # start a fresh copy as itself. Never leave a double-click with nothing.
            if args.show:
                try:
                    import subprocess as _sp
                    import time as _t2
                    import json as _json
                    # 1. one last polite ask over the socket: its thread may still
                    #    understand "quit" even when the window cannot.
                    try:
                        import socket as _sk
                        with _sk.create_connection(("127.0.0.1", port),
                                                   timeout=1.0) as _sock:
                            _sock.sendall(_json.dumps(
                                {"event": "quit", "from": "relaunch"}
                            ).encode("utf-8") + b"\n")
                    except OSError:
                        pass
                    _t2.sleep(2.0)
                    # 2. still holding the port? name the holder and end it.
                    holder = _holder_pid(port)
                    if holder and _port_live(port):
                        _record_stop(holder)
                        try:
                            if sys.platform == "win32":
                                _sp.run(["taskkill", "/F", "/PID", str(holder)],
                                        capture_output=True, timeout=15)
                            else:
                                os.kill(holder, 15)
                        except Exception:                        # noqa: BLE001
                            pass
                        _t2.sleep(1.0)
                    if not _port_live(port):
                        fresh = [sys.executable] + (
                            ["run.py", "--show"]
                            if not getattr(sys, "frozen", False) else ["--show"])
                        _sp.Popen(fresh, cwd=str(ROOT))
                        logs.note("BOOT · a stuck copy held the lock; closed it "
                                  "(pid %s) and a fresh JARVIS is starting" % holder)
                        print("JARVIS was stuck; closed the stuck copy and a fresh "
                              "one is starting.")
                        return _finish(0)
                except Exception:                                # noqa: BLE001
                    pass
            message = (f"port {port} is held but nothing answered. JARVIS is not "
                       f"running properly — close it with Ctrl+Alt+Q, or run "
                       f"tools\\jarvis_state.py --kill-stale, then start again")
            print(message)
            logs.note("BOOT · " + message)
            return _finish(3)

    app = QApplication([argv[0]] + qt_args)

    # Say something immediately. A cold start on Windows spends a second or two loading
    # DLLs, and silence during that reads as "it did not open".
    import time as _time
    _started = _time.time()
    splash = None
    if not (args.shadow or dev_run):
        try:
            from arcdesk.widgets.splash import Splash
            splash = Splash("JARVIS")
            splash.show()
            app.processEvents()
            # hard ceiling: a card that outlives a failed start would sit on the desktop
            from PySide6.QtCore import QTimer as _QTimer
            _QTimer.singleShot(8000, splash.close)
        except Exception:                                        # noqa: BLE001
            splash = None
    app.setApplicationName("Arc Desk")
    app.setApplicationDisplayName("Arc Desk")
    app.setOrganizationName("ArcDesk")
    app.setQuitOnLastWindowClosed(False)   # we live in the tray

    # ---- close cleanly when something asks us to ---------------------------
    # Ctrl+C in a console, `taskkill` (without /F), a service stop or a stopped build
    # all arrive as a signal. Unhandled, Python prints a KeyboardInterrupt traceback
    # and skips the instance-lock release and the magic-mode journal restore, so the
    # *next* launch would believe Arc Desk is already running.
    #
    # This is installed right after the QApplication and BEFORE the first-run wizard,
    # because that wizard runs its own nested event loop — the first version of this
    # code sat after it and therefore could never answer a signal sent while the user
    # was still reading the setup cards (measured: exit -15, no clean shutdown).
    #
    # A Python signal handler must not touch Qt directly, so it only sets a flag and a
    # small timer in the GUI thread performs the quit.
    import signal as _signal

    stop_request: dict[str, int] = {"signal": 0}

    def _ask_to_quit(signum, _frame) -> None:
        stop_request["signal"] = int(signum)

    for _sig in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"):
        _name = getattr(_signal, _sig, None)
        if _name is not None:
            try:
                _signal.signal(_name, _ask_to_quit)
            except (ValueError, OSError):
                pass

    def _watch_for_stop() -> None:
        if not (stop_request["signal"] or stop_request.get("asked")):
            return
        # Any dialog still on screen is rejected explicitly, which is what lets the
        # setup loop below fall out immediately. Without it, a stop signal sent while
        # the first-run wizard was open left the process alive for another 12 s and it
        # had to be killed (measured in the sandbox, before the loop was rewritten).
        for widget in app.topLevelWidgets():
            try:
                if isinstance(widget, QDialog) and widget.isVisible():
                    widget.reject()
            except Exception:
                pass
        app.quit()

    _heartbeat = QTimer(app)
    _heartbeat.setInterval(200)
    _heartbeat.timeout.connect(_watch_for_stop)
    _heartbeat.start()


    logs.install_qt()
    # NOTE: the "last time it did not close properly" line is added AFTER the window
    # exists (see below). Putting it here referenced `window` before it was created, so a
    # launch that followed an unclean exit died with a NameError and no window at all —
    # exactly "close pannadhum app open aagala".
    win = MainWindow(cfg)
    if inst is not None:
        # emit, don't call: the lock socket is served by a plain thread, and Qt
        # widgets may only be touched from the GUI thread. A signal hops over.
        win.summon_requested.connect(win.summon)
        inst.on_summon = win.summon_requested.emit
        # "quit" over the lock socket: an updater or launcher asking us to close. The
        # socket runs on its own thread, so it only sets a flag; the 200 ms heartbeat
        # (already on the GUI thread) turns that into a normal quit — settings saved,
        # session marked clean, nothing killed.
        inst.on_quit = lambda: stop_request.__setitem__("asked", True)
        app.aboutToQuit.connect(inst.release)

    if _unclean:
        streak = logs.crash_streak()
        bundle = logs.crash_bundle()
        told = _unclean + (f" — a file you can send is here: {bundle}" if bundle else "")
        _prefix = "LAUNCHER · " if logs.last_session_was_launcher_stop else "CRASH · "
        try:
            win.console.add_note(_prefix + told)
        except Exception:                                        # noqa: BLE001
            logs.note(_prefix + told)
        if streak >= 2:
            # "yethavathu select pana application crash aagi close aaguthu" twice in a row
            # means this launch has to work, or the app is unusable: start with the heavy
            # visuals paused (a GPU driver that dies on the deck crashes before the window
            # is even drawn) and say so. Nothing is written to the person's settings.
            try:
                cfg["effects"] = 0.0
                cfg["shadow"]["effects"] = 0.0
                win.set_effects(0.0)
                msg = (f"the last {streak} runs ended unexpectedly, so this one starts "
                       f"with the heavy visuals paused — JARVIS works normally, and the "
                       f"effects can be turned back on in Settings once the cause is found")
                win.console.add_note("SAFE · " + msg)
                logs.note("SAFE · " + msg)
            except Exception:                                    # noqa: BLE001
                pass

    from arcdesk.tray import ArcTray, reactor_icon
    win.setWindowIcon(reactor_icon(cfg["mode"]))
    tray = None
    want_tray = bool(cfg.get("shadow", {}).get("tray", True)) and not args.no_tray
    if want_tray and QSystemTrayIcon.isSystemTrayAvailable():
        tray = ArcTray(win)
        tray.show()
        app.setProperty("arc_tray", True)

    # Stealth is decided here, once, and the decision is written to the log. A hidden
    # app that says nothing is indistinguishable from an app that crashed, which is the
    # report that started this: "it installs, but it does not work".
    hidden_boot = (args.shadow or win.shadow) and not args.show
    if hidden_boot and tray is None and not args.no_tray:
        hidden_boot = False
        logs.note("BOOT · stealth was asked for, but this system gave no tray icon — "
                  "showing the window instead of hiding with nothing to click")
    if hidden_boot:
        win.hide()
        logs.note("BOOT · stealth: the window is not shown (that is what --shadow asks "
                  "for). Ctrl+Alt+J opens it; the tray icon is the other handle")
    else:
        win.show()
        logs.note("BOOT · the window is shown")
        try:
            from arcdesk.logs import env_line
            logs.note("BOOT · environment: " + env_line())
        except Exception:                                        # noqa: BLE001
            pass
        # The pinned Qt is a specific fixed version; a shortcut that skips JARVIS.bat
        # can still be running an older one. Say so, once, in words — the .bat tops the
        # libraries up the next time it is the one that starts the app.
        try:
            import PySide6 as _p6
            import re as _re
            _pin = ""
            _req = Path(__file__).with_name("requirements.txt")
            if _req.exists():
                _m = _re.search(r"^PySide6-Essentials==([0-9.]+)",
                                _req.read_text(encoding="utf-8"), _re.M)
                _pin = _m.group(1) if _m else ""
            if _pin and _p6.__version__ != _pin:
                logs.note(f"BOOT · the Qt version is {_p6.__version__}, but this build pins "
                          f"{_pin} — run JARVIS.bat once (it updates the libraries itself)")
                win.console.add_note(
                    "SETUP · this build wants Qt " + _pin + " and this copy is running "
                    + _p6.__version__ + " — double-click JARVIS.bat once; it updates the "
                    "libraries by itself, then JARVIS starts as usual.")
        except Exception:                                        # noqa: BLE001
            pass
        if splash is not None:                 # the real window is up; the card can go
            try:
                splash.close()
            except Exception:                                    # noqa: BLE001
                pass
            splash = None
        logs.note("BOOT · %.1f s from the double-click to the window"
                  % (_time.time() - _started))
    # Two one-time background costs, paid where nobody can feel them: the Windows
    # voice list (one PowerShell call) and the engine sweep (which on a machine that
    # already installed an engine can take minutes). The drawing thread must never
    # pay for either — it only ever reads what these have already found.
    def _warm_background() -> None:
        try:
            from arcdesk.ai import voice as _voice
            _voice.voice_names_ensure()
        except Exception:                                         # noqa: BLE001
            pass
        try:
            time.sleep(40)                 # let the boot finish before the sweep starts
            from arcdesk import clone as _clone
            _clone.engines(cached_only=False)
        except Exception:                                         # noqa: BLE001
            pass
    try:
        threading.Thread(target=_warm_background, daemon=True,
                          name="arc-warm").start()
    except Exception:                                        # noqa: BLE001
        pass
    # "laptop off, laptop on, JARVIS must be there": an autostart entry survives a move of
    # the folder as a path that no longer exists — it still looks registered, and nothing
    # starts. Repair only what is already switched on; never switch it on from here.
    try:
        from arcdesk import autostart as _autostart
        _fixed = _autostart.repair()
        if _fixed.get("action") == "repaired":
            logs.note("BOOT · start-with-the-computer pointed at a folder that is gone "
                      "(%s) — repaired to %s" % (_fixed.get("was"), _fixed.get("now")))
            win.console.add_note(
                "SETUP · start with Windows was pointing at an old folder — repaired, it "
                "now starts THIS one. Nothing else changed.")
        elif _fixed.get("action") == "failed":
            logs.note("BOOT · start-with-the-computer could not be repaired (%s) — run "
                      "AUTO-START.bat" % _fixed.get("error", ""))
        # First launch on this copy: switch it ON rather than hoping someone finds the
        # checkbox. Reversible from Settings, the tray, or AUTO-START.bat.
        _first = _autostart.ensure_first_time()
        if _first.get("action") == "enabled":
            logs.note("BOOT · start-with-the-computer switched ON for %s"
                      % _first.get("folder"))
            win.console.add_note(
                "SETUP · JARVIS will now start by itself, hidden, when Windows starts "
                "(Ctrl+Alt+J opens it). Turn it off any time in Settings.")
        elif _first.get("action") == "failed":
            logs.note("BOOT · could not switch on start-with-the-computer (%s) — run "
                      "AUTO-START.bat" % _first.get("error", ""))
    except Exception as _exc:                                    # noqa: BLE001
        logs.note("BOOT · the autostart check did not run (%s) — the app runs anyway"
                  % type(_exc).__name__)

    # A download thread must be stopped BEFORE Qt tears the application down. Without this
    # the process ends with "QThread: Destroyed while thread is still running", which is a
    # hard abort — the app "closes by itself" with no Python traceback (fault.log empty).
    try:
        from arcdesk.widgets import engine_dialog as _ed
        app.aboutToQuit.connect(lambda: _ed.stop_all_workers())
        from arcdesk.widgets import qsafe
        app.aboutToQuit.connect(lambda: qsafe.stop_all())
    except Exception:                                            # noqa: BLE001
        pass

    # "desktop shortcut um ila, proper ah open panra options um ila": a first launch used to
    # end with nothing to click, so opening JARVIS meant remembering a .bat file. The
    # shortcut is made once, kept pointing at THIS folder, and never argued with — if the
    # person deletes it, it comes back quietly once; the Settings checkbox turns it off.
    try:
        from arcdesk import shortcut_offer as _shortcuts
        _sc = _shortcuts.ensure()
        if _sc.get("action") in ("create", "restore", "repair"):
            logs.note("BOOT · shortcut %s for %s" % (_sc.get("action"),
                                                     ", ".join(_sc.get("made") or [])))
            win.console.add_note(
                "SETUP · JARVIS is now on your Desktop and in the Start Menu — one click, "
                "no black window. (If the folder ever moves, the next launch fixes it.)")
        elif _sc.get("action") == "failed":
            logs.note("BOOT · the shortcut could not be made (%s) — run CREATE-SHORTCUT.bat"
                      % _sc.get("why", ""))
    except Exception as _exc:                                    # noqa: BLE001
        logs.note("BOOT · the shortcut check did not run (%s) — the app runs anyway"
                  % type(_exc).__name__)

    # Two guards that turn "it hung again" into a line in the log, from now on:
    #   * the stall watch notices when the drawing thread was not allowed to run, and
    #     writes down the line it was stuck in;
    #   * the blocking guard (opt-in, ARCDESK_UI_GUARD=1) writes down anything that
    #     starts a child process, opens a socket or sleeps on that thread.
    # The cursor sweep is the fix for the actual screenshot: a waiting cursor nobody
    # put back. Only arcdesk.uiwork may set one, so when no job is running there is none.
    try:
        from arcdesk import uiwork as _uiwork
        _uiwork.install()
        _uiwork.install_cursor_hygiene()
        from arcdesk import blockguard as _blockguard
        _blockguard.install()          # off unless ARCDESK_UI_GUARD is set: warn or strict
    except Exception as _exc:                                    # noqa: BLE001
        logs.note("BOOT · the UI guards did not start (%s) — the app runs anyway"
                  % type(_exc).__name__)

    logs.note("BOOT · handles: tray=%s, hotkeys=%s, stealth=%s"
              % ("yes" if tray is not None else "no",
                 "yes" if cfg.get("shadow", {}).get("hotkeys", True) else "no",
                 "on" if hidden_boot else "off"))

    if getattr(args, "download_voice_model", False):
        # The installer offers this as a post-install tick: without the 40 MB speech
        # model and the 30 MB speaker model, "hey jarvis" cannot work on a fresh
        # machine — so the download is one visible step, not a mystery failure later.
        import subprocess as _sp
        from arcdesk import paths as _paths
        from arcdesk import voiceid as _voiceid
        ok_all = True
        print("[1/2] speech model (Vosk, ~40 MB) …")
        try:
            cmd, kwargs = _paths.daemon_command(8765, "hey jarvis", "auto", "bye jarvis",
                                                extra=["--download-model"])
            done = _sp.run(cmd, timeout=1800, **kwargs)
            ok_all &= done.returncode == 0
        except Exception as exc:                                # noqa: BLE001
            ok_all = False
            print(f"      failed: {type(exc).__name__}: {exc}")
        print("[2/2] speaker model (voice lock, ~30 MB) …")
        got = _voiceid.download_model()
        print("      " + got["message"])
        ok_all &= bool(got["ok"])
        print("done." if ok_all else "some downloads failed — Settings → Voice can retry.")
        return _finish(0 if ok_all else 1)

    if args.console:
        win.toggle_console(True)

    # first run: one card, three decisions, the evidence next to each one
    if cfg.get("first_run", True) and not (args.screenshot or args.demo_chat or args.ask):
        try:
            from arcdesk import firstrun
            from arcdesk.ai import backends
            from arcdesk.widgets.welcome import WelcomeDialog

            # The probe opens a socket to ~10 local ports. Doing it here froze the window
            # that had just appeared, which is the worst possible moment — so it runs on a
            # thread while a real event loop keeps painting (`time.sleep` + processEvents
            # is not a substitute: it processes events, it does not let anything paint
            # between two sleeps on a busy machine).
            probed: dict = {}
            probe_done = threading.Event()

            def _probe() -> None:
                try:
                    probed["engines"] = [d.describe() for d in backends.probe()]
                except Exception:                                # noqa: BLE001
                    probed["engines"] = []
                probe_done.set()

            threading.Thread(target=_probe, name="arc-backend-probe", daemon=True).start()
            first_loop = QEventLoop()

            def _probe_finished() -> None:
                if probe_done.is_set():
                    first_loop.quit()

            probe_beat = QTimer()
            probe_beat.setInterval(50)
            probe_beat.timeout.connect(_probe_finished)
            probe_beat.start()
            QTimer.singleShot(2500, first_loop.quit)     # never wait longer than this
            first_loop.exec()
            probe_beat.stop()

            dlg = WelcomeDialog(cfg, win.voice, probed.get("engines", []), parent=win)
            # Not dlg.exec(): a nested event loop of its own cannot be left cleanly when
            # a stop signal arrives mid-setup (measured: SIGBUS on teardown). A plain
            # QEventLoop keeps the card modal in practice and makes a stop request just
            # fall out of the loop — with no sleeping on the drawing thread.
            setup_loop = QEventLoop()
            dlg.finished.connect(setup_loop.quit)

            def _stop_asked() -> None:
                if stop_request["signal"] or not dlg.isVisible():
                    setup_loop.quit()

            setup_beat = QTimer()
            setup_beat.setInterval(100)
            setup_beat.timeout.connect(_stop_asked)
            setup_beat.start()
            dlg.show()
            setup_loop.exec()
            setup_beat.stop()
            if not dlg.isVisible():
                pass
            result = getattr(dlg, "setup_result", None)
            if result:
                # say what was actually set, in the console, where it can be read again
                for line in firstrun.summary(result).splitlines():
                    win.console.add_note(line)
                # ...and make the choice TRUE right now: choosing "voice" means the ears
                # start in this same session, not after the next login.
                if cfg.get("wake", {}).get("enabled"):
                    win._set_wake_pill(True)
                    win._start_wake()
                else:
                    win._stop_wake()
                # ...and be VISIBLE. Stealth hides the window at boot, and after the card
                # was answered that read as "the app did not open" (the user's report).
                # Answering a setup card means somebody is looking at the screen.
                if firstrun.reveal_window(True, hidden_boot):
                    win.show()
                    win.raise_()
                    win.activateWindow()
                if cfg.get("wake", {}).get("enabled"):
                    win.console.add_note('SETUP · listening for "hey jarvis" — say '
                                         '"bye jarvis" to put me away. Ctrl+Alt+J opens '
                                         'this window any time.')
                else:
                    win.console.add_note("SETUP · icon mode: nothing listens in the "
                                         "background. Click me (or Ctrl+Alt+J) whenever "
                                         "you need something.")
        except Exception as exc:                                # noqa: BLE001
            # Silence here is the worst outcome: on a fresh install the setup card is the
            # only thing on screen, and a swallowed exception meant "nothing opened".
            logs.note(f"SETUP · the welcome card could not open "
                      f"({type(exc).__name__}: {exc}) — showing the main window instead")
            win.show()
            win.raise_()

    # "which file mentions X" only works once something has been read. Do it once, in
    # the background, so the window is never blocked by somebody's 4,000 PDFs.
    if cfg.get("docs", {}).get("index_on_start") and not (args.screenshot or args.ask):
        from arcdesk import docs_worker
        docs_worker.start(win)

    if args.demo_chat or args.ask:
        win.toggle_console(True)
        if args.demo_chat:
            c = win.console
            c.add_user("what is my cpu doing, and open notepad")
            c.add_tool("system_report", "{}",
                       "cpu 18% (8 threads); ram 61% used, 3.1 GB free of 7.9 GB; "
                       "disk 74% used, 61 GB free; battery 88% charging")
            c.add_tool("open_app", '{"app": "notepad"}', "launched notepad")
            c.add_arc("CPU is sitting at eighteen percent and RAM at sixty one. "
                      "Notepad is open. Nothing is choking the machine right now.")
        if args.ask:
            import PySide6.QtCore as _qc

            answer: dict[str, str] = {}
            win.console.add_user(args.ask)
            win.agent.reply.connect(lambda t: (answer.setdefault("text", t),))
            win.agent.error.connect(lambda e: answer.setdefault("error", e))
            loop = _qc.QEventLoop()
            win.agent.reply.connect(lambda *_: loop.quit())
            win.agent.error.connect(lambda *_: loop.quit())
            _qc.QTimer.singleShot(60_000, loop.quit)
            win.agent.ask(args.ask)
            loop.exec()
            for _ in range(6):
                app.processEvents()
            if answer.get("error"):
                print("[error]", answer["error"])
            print("[JARVIS]", answer.get("text", "(no answer)"))
            return _finish(0 if answer.get("text") else 2)

    if args.awaken_shot:
        from arcdesk.widgets.awakening import Awakening
        aw = Awakening(win.theme, "JARVIS // ONLINE")
        aw.show()
        for _ in range(4):
            app.processEvents()
        aw.advance(1.05)
        for _ in range(4):
            app.processEvents()
        ok = aw.grab().save(args.awaken_shot)
        print(("saved " if ok else "failed to save ") + args.awaken_shot)
        return _finish(0 if ok else 1)

    if args.palette_shot:
        win.palette.set_theme(win.theme)
        win.palette.set_brain(win.agent.describe())
        win.palette.popup()
        win.palette.input.setText("open google")
        win.palette.show_line("› open google")
        win.palette.show_line("launched https://www.google.com")
        for _ in range(6):
            app.processEvents()
        ok = win.palette.grab().save(args.palette_shot)
        print(("saved " if ok else "failed to save ") + args.palette_shot)
        return _finish(0 if ok else 1)

    if args.magic_shot:
        win._magic_screen = win._magic_screen or __import__(
            "arcdesk.widgets.magicscreen", fromlist=["MagicScreen"]).MagicScreen(
            win.theme, "bye jarvis")
        ms = win._magic_screen
        ms.resize(1440, 900)
        ms.show()
        for _ in range(4):
            app.processEvents()
        ms.advance(2.4)
        ms.set_status("MAGIC MODE ACTIVE - ASK ME ANYTHING")
        for _ in range(6):
            app.processEvents()
        ok = ms.grab().save(args.magic_shot)
        print(("saved " if ok else "failed to save ") + args.magic_shot)
        return _finish(0 if ok else 1)

    if args.charms_shot:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
        win.show_charms(True)
        win.overlay.resize(1280, 720)
        win.overlay.show()
        for _ in range(4):
            app.processEvents()
        win.overlay.advance(2.2)
        for _ in range(4):
            app.processEvents()

        # composite over a mock Windows desktop so the shot reads properly
        canvas = QPixmap(1280, 720)
        canvas.fill(QColor("#0b1a2b"))
        cp = QPainter(canvas)
        cp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        g = QLinearGradient(0, 0, 1280, 720)
        g.setColorAt(0.0, QColor("#0d2137"))
        g.setColorAt(0.55, QColor("#123049"))
        g.setColorAt(1.0, QColor("#0a1622"))
        cp.fillRect(0, 0, 1280, 720, g)
        cp.setPen(QColor(255, 255, 255, 28))
        for i in range(9):          # pretend desktop icons
            cp.setBrush(QColor(255, 255, 255, 22))
            cp.drawRoundedRect(QRectF(34, 34 + i * 88, 48, 40), 6, 6)
        cp.setBrush(QColor(10, 16, 24, 235))   # pretend taskbar
        cp.setPen(QColor(255, 255, 255, 18))
        cp.drawRect(QRectF(0, 676, 1280, 44))
        cp.end()
        overlay_pix = win.overlay.grab()
        cp = QPainter(canvas)
        cp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        cp.drawPixmap(0, 0, overlay_pix)
        cp.end()
        ok = canvas.save(args.charms_shot)
        print(("saved " if ok else "failed to save ") + args.charms_shot)
        return _finish(0 if ok else 1)

    if args.palette:
        win.palette.popup()

    if args.screenshot:
        for _ in range(8):
            app.processEvents()
        win.advance(args.advance)
        for _ in range(4):
            app.processEvents()
        ok = win.grab().save(args.screenshot)
        print(("saved " if ok else "failed to save ") + args.screenshot)
        return _finish(0 if ok else 1)

    if stop_request["signal"]:
        # We were asked to stop before the main loop was ever entered (typically while
        # the first-run wizard was still on screen). Leave nothing holding the lock.
        #
        # Deliberately no win.close() here: the dialog had just been rejected from inside
        # a timer callback, and closing the window as well crashed the interpreter on the
        # way out (measured: SIGBUS, exit 135, three times out of three). Returning is
        # enough — Qt tears the rest down itself and the instance lock is a socket, so it
        # is released by the OS even if a later teardown were to fault.
        _heartbeat.stop()
        logs.end_session()
        print("Arc Desk closed cleanly.", flush=True)
        return _finish(0)

    rc = app.exec()
    _heartbeat.stop()
    logs.end_session()          # this was a normal close, not a crash
    if tray is not None:
        tray.hide()
    if stop_request["signal"]:
        print("Arc Desk closed cleanly.", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
