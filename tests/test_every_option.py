"""Open EVERY option and see which one takes the app down

    python tests/test_every_option.py            # in-process: exceptions, and the ones that kill us
    python tests/test_every_option.py --crashy   # also runs each dialog in its own process, so a
                                                 # hard abort (segfault / QThread destroy) is a
                                                 # NAME, not a silent death

Why this file exists
--------------------
"YENTHA OPTIONS KULA PONALUM AUTO CRASH MATHIRI CLOSE AAGUTHU" — every option closes it. A crash
in a dialog is not something you find by reading one dialog: it is something one of the eleven
dialogs does that every option shares. So this walks all of them, in a fresh window, one at a
time, and reports per option:

    opened        the dialog built and exec() ran (it is closed by a timer, like Esc)
    built         construction raised nothing
    survived      no unhandled exception while it was on screen
    exit          if it is run as its own process: 0 = clean, <0 = killed by a signal

Nothing here needs a network, a microphone, a model or Windows. `ARCDESK_OFFLINE=1` makes the
network calls fail fast instead of hanging, which is the same thing the app does when it has no
connection — and a dialog must survive having no connection.
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-options-")
os.environ["ARCDESK_NO_FOREIGN_PYTHON"] = "1"
os.environ.setdefault("ARCDESK_NO_WAKE", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<56} {str(got)[:46]!r}")
    if not same:
        print(f"        expected {want!r}")


def pump(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(max(1, int(seconds * 1000)), loop.quit)
    loop.exec()


# --------------------------------------------------------------------------- one option
#: (name, module, class) — every window the app can put on screen.
OPTIONS = [
    ("settings",         "arcdesk.widgets.settings",       "SettingsDialog"),
    ("brain (AI setup)", "arcdesk.widgets.brain_dialog",   "BrainDialog"),
    ("engines",          "arcdesk.widgets.engine_dialog",  "EngineDialog"),
    ("voice library",    "arcdesk.widgets.voicelib_dialog", "VoiceLibraryDialog"),
    ("voice lock",       "arcdesk.widgets.voicelock",      "VoiceLockDialog"),
    ("ears (mic test)",  "arcdesk.widgets.ears_dialog",    "EarsDialog"),
    ("awakening (wake)", "arcdesk.widgets.awakening",      "Awakening"),
    ("shortcut shelf",   "arcdesk.widgets.shortcuts",      "ShortcutShelf"),
    ("art window",       "arcdesk.widgets.artview",        "ArtWindow"),
    ("holo deck",        "arcdesk.widgets.holo",           "HoloWindow"),
    ("magic screen",     "arcdesk.widgets.magicscreen",    "MagicScreen"),
    ("companion",        "arcdesk.widgets.companion",      "Companion"),
]


def open_one(name: str, module: str, cls: str, seconds: float = 2.5) -> dict:
    """Build one dialog, run it like the app does, and report what happened."""
    import importlib
    from arcdesk import config
    from arcdesk.theme import get_theme

    out = {"name": name, "built": False, "survived": False, "error": "", "trace": ""}
    errors: list = []

    def hook(tp, val, tb):                                   # noqa: ANN001
        errors.append(f"{tp.__name__}: {val}")
        if len(errors) == 1:
            out["trace"] = "".join(traceback.format_exception(tp, val, tb))[-1400:]

    real_hook = sys.excepthook
    sys.excepthook = hook
    widget = None
    try:
        mod = importlib.import_module(module)
        klass = getattr(mod, cls)
        cfg = config.load()
        theme = get_theme("chill")
        # Construct by parameter NAME. Guessing the order fed a Theme where a cfg dict was
        # expected and produced "AttributeError: 'dict' object has no attribute 'panel'" — a
        # bug in the test, not in the app.
        import inspect
        try:
            params = inspect.signature(klass.__init__).parameters
        except (TypeError, ValueError):
            params = {}
        supplied = {"cfg": cfg, "config": cfg, "theme": theme, "parent": None,
                    "on_pick": None, "on_done": None, "done": None}
        kwargs = {}
        for name_, param in list(params.items())[1:]:
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            if name_ in supplied:
                kwargs[name_] = supplied[name_]
            elif param.default is param.empty:
                kwargs[name_] = None
        try:
            widget = klass(**kwargs)
        except Exception:                                     # noqa: BLE001
            widget = klass(cfg, theme)
        out["built"] = widget is not None
        if widget is None:
            out["error"] = "could not construct with any known signature"
            return out
        widget.show()
        pump(0.4)
        # a QDialog with exec() is closed by the timer; a plain window by close()
        if isinstance(widget, QDialog):
            QTimer.singleShot(int(seconds * 1000), widget.reject)
            widget.exec()
        else:
            pump(seconds)
        pump(0.3)
        out["survived"] = not errors
        if errors:
            out["error"] = errors[0]
    except Exception as exc:                                  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["trace"] = traceback.format_exc()[-1400:]
    finally:
        sys.excepthook = real_hook
        try:
            if widget is not None:
                widget.close()
                widget.deleteLater()
                pump(0.2)
        except Exception:                                     # noqa: BLE001
            pass
    return out


def main() -> int:
    app = QApplication.instance() or QApplication([])
    crashy = "--crashy" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]

    print("\n=== which option closes JARVIS ===\n")
    bad = []
    for name, module, cls in OPTIONS:
        if only and name not in only:
            continue
        res = open_one(name, module, cls)
        verdict = "OK" if (res["built"] and res["survived"]) else "PROBLEM"
        if verdict != "OK":
            bad.append(res)
        print(f"   {verdict:<8} {name:<20} "
              f"built={'yes' if res['built'] else 'NO '} "
              f"survived={'yes' if res['survived'] else 'NO '} {res['error'][:60]}")
        if res["trace"]:
            for line in res["trace"].strip().splitlines()[-6:]:
                print(f"            {line}")

    if crashy:
        print("\n=== the same options, each in its own process (a hard abort shows up here) ===")
        import subprocess
        for name, module, cls in OPTIONS:
            if only and name not in only:
                continue
            t0 = time.perf_counter()
            proc = subprocess.run(                                   # noqa: PLW1510
                [sys.executable, __file__, name], cwd=str(ROOT),
                capture_output=True, text=True, timeout=180)
            took = time.perf_counter() - t0
            tail = (proc.stdout.strip().splitlines() or [""])[-1]
            alive = proc.returncode == 0
            print(f"   {'OK  ' if alive else 'DEAD'} {name:<20} exit={proc.returncode:<4} "
                  f"{took:4.1f}s  {tail[:40]}")
            if not alive:
                bad.append({"name": name, "error": f"exit {proc.returncode}",
                            "trace": (proc.stderr or "")[-900:]})

    print()
    check("every option opens and closes without taking the app down", len(bad), 0)
    if bad:
        print("\nwhat failed:")
        for res in bad:
            print(f"\n--- {res['name']}: {res['error']}")
            if res["trace"]:
                print(res["trace"])
    print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
