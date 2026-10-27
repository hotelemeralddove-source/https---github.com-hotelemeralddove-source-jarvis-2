"""The plumbing added in the audit: crash log, single instance, doctor, paths.

These are the things that decide whether a *packaged* app is reportable or just
"it didn't open". Each one is checked here so a regression is caught on Linux
instead of on the user's laptop.

Run:  python tests/test_system.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from arcdesk import config, instance, logs  # noqa: E402


def main() -> int:
    ok = True

    # ---------- 1. portable / isolated settings folder ----------------
    home = os.environ["ARCDESK_HOME"]
    inside = str(config.data_dir()) == home
    paths_ok = str(config.settings_path()).startswith(home)
    print(f"1) ARCDESK_HOME honoured : data_dir={inside}, settings_path={paths_ok}  "
          f"{'OK' if inside and paths_ok else 'FAIL'}")
    ok &= inside and paths_ok

    # ---------- 2. crash log writes and never leaks a key -------------
    import logging
    path = logs.install()
    secret = "sk-abcdefghijklmnop1234567890"
    logging.getLogger("arcdesk.test").error("provider failed with key %s", secret)
    text = ""
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except Exception:
        pass
    wrote = "provider failed" in text
    leaked = secret in text
    scrubbed = "sk-***" in text
    print(f"2) crash log             : wrote={wrote}, scrubbed={scrubbed}, "
          f"leaked={leaked}  {'OK' if wrote and not leaked else 'FAIL'}")
    ok &= wrote and not leaked

    # ---------- 3. single instance ------------------------------------
    cfg = {"wake": {"port": 8971}, "instance": {}}
    first = instance.Instance(cfg)
    got_first = first.acquire()
    second = instance.Instance(cfg)
    got_second = second.acquire()

    hits: list[float] = []
    first.on_summon = lambda: hits.append(time.time())
    told = instance.another_instance_running(cfg)
    for _ in range(40):                      # the listener thread needs a moment
        if hits:
            break
        time.sleep(0.05)
    second.release()
    first.release()
    good = got_first and not got_second and told and bool(hits)
    print(f"3) single instance       : first={got_first}, second={got_second}, "
          f"summon_delivered={bool(hits)}  {'OK' if good else 'FAIL'}")
    ok &= good

    # ---------- 4. doctor runs and reports ---------------------------
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import doctor
    code = doctor.run(verbose=False)
    rows = list(doctor._rows)
    statuses = {s for s, _, _ in rows}
    sane = len(rows) >= 8 and statuses <= {doctor.PASS, doctor.WARN, doctor.FAIL,
                                           doctor.INFO}
    print(f"4) doctor                : {len(rows)} checks, exit={code}, "
          f"statuses={sorted(statuses)}  {'OK' if sane else 'FAIL'}")
    ok &= sane

    # ---------- 4b. a clean machine must pass its own doctor ---------
    # Regression: "auto" was classified as a paid provider, so a brand-new
    # install failed its own doctor. On a keyless machine auto resolves to lite.
    for var in ("OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
        os.environ.pop(var, None)
    clean = doctor.run(verbose=False)
    guard = next((d for st, n, d in doctor._rows if n == "Cost guard"), "")
    clean_ok = clean == 0 and "PAID" not in guard
    print(f"4b) keyless doctor       : exit={clean}, {guard[:48]}  "
          f"{'OK' if clean_ok else 'FAIL'}")
    ok &= clean_ok

    # ---------- 5. summon exists on the window -----------------------
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([sys.argv[0]])
    from arcdesk.widgets.window import MainWindow
    cfg2 = config.load()
    cfg2.update({"mode": "chill", "charms": {"enabled": False, "items": []},
                 "wake": {"enabled": False, "port": 8973, "autostart_daemon": False},
                 "shadow": {"enabled": True, "awaken": False, "hotkeys": False,
                            "tray": False, "bye_action": "hide"},
                 "magic": {"enabled": False},
                 "ai": {"enabled": True, "provider": "lite", "voice": False}})
    win = MainWindow(cfg2)
    has_signal = hasattr(win, "summon_requested") and hasattr(win, "summon")
    win.summon()                       # must not raise with magic mode off
    print(f"5) summon signal         : {has_signal}  {'OK' if has_signal else 'FAIL'}")
    ok &= has_signal
    win.shutdown()

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
