#!/usr/bin/env python3
"""Arc Desk doctor — check that this install can actually work.

    python tools\\doctor.py           (or: python run.py --doctor)

Every check answers "will the thing I promised the user actually happen on this
machine?". It prints PASS / WARN / FAIL and never changes anything: read-only,
offline, no admin rights, no network except a 250 ms localhost port probe.

Exit code: 0 when nothing FAILED (warnings are fine), 1 when something did.
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"
_rows: list[tuple[str, str, str]] = []


def add(status: str, name: str, detail: str = "") -> None:
    _rows.append((status, name, detail))


# --------------------------------------------------------------- the checks
def check_python() -> None:
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        add(PASS, "Python version", ver)
    else:
        add(FAIL, "Python version", f"{ver} — Arc Desk needs 3.10 or newer")


def check_qt() -> None:
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        add(PASS, "PySide6 (GUI toolkit)", f"{PySide6.__version__} · Qt {qVersion()}")
    except Exception as exc:
        add(FAIL, "PySide6 (GUI toolkit)",
            f"missing ({type(exc).__name__}) — pip install -r requirements.txt")


def check_config() -> None:
    from arcdesk import config
    try:
        d = config.data_dir()
        probe = d / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        add(PASS, "Settings folder", str(d))
    except Exception as exc:
        add(FAIL, "Settings folder", f"not writable: {type(exc).__name__}: {exc}")
        return

    cfg = config.load()
    keys = set(cfg)
    expected = set(config.DEFAULTS)
    missing = expected - keys
    unknown = keys - expected - {"_force_show"}
    if missing:
        add(WARN, "settings.json", f"{len(missing)} new default(s) added automatically: "
                                   f"{', '.join(sorted(missing)[:5])}")
    elif unknown:
        add(INFO, "settings.json", f"valid · extra keys: {', '.join(sorted(unknown)[:5])}")
    else:
        add(PASS, "settings.json", "valid and complete")

    # The look of the world is a real cost, so it is reported like one.
    from arcdesk.theme import tuned
    eff = cfg.get("effects")
    mode = str(cfg.get("mode") or "chill")
    th = tuned(mode, eff)
    where = "follows the mode" if eff is None else f"set to {float(th.effects):.2f}"
    add(PASS, "Visual effects", f"{where} · mode '{mode}' draws at {th.effects:.2f}"
                                f" ({th.fps} fps cap)")


def check_cost() -> None:
    """Is the configured brain actually free — after 'auto' is resolved?

    'auto' is the default and it is not a provider: it picks the first usable
    brain, cheapest first (custom -> groq -> gemini -> openai -> local -> lite).
    Classifying the literal string "auto" as paid was wrong and made a healthy
    machine fail its own doctor, so it is resolved first, exactly like llm.py.
    """
    from arcdesk import config
    from arcdesk.ai import cost, llm
    cfg = config.load()
    ai = cfg.get("ai", {}) or {}
    limit = str((cfg.get("cost", {}) or {}).get("max_class", cost.MAX_DEFAULT))
    raw = str(ai.get("provider") or "auto").strip()
    try:
        resolved = llm.detect_provider(ai) if raw == "auto" else raw
    except Exception:
        resolved = "lite"
    cls = cost.classify(resolved, str(ai.get("base_url") or ""))
    label = raw if raw == resolved else f"{raw} → {resolved}"

    if cls == cost.CLASS_PAID and not cost.allowed(cls, limit):
        # The guard refuses before any request and the agent falls back to Lite,
        # so the app keeps working — that is a warning about expectations, not a
        # broken install.
        add(WARN, "Cost guard",
            f"brain {label} is PAID but the limit is '{limit}' — it will be refused "
            "and ARC will answer with Lite instead. Set provider=lite (or ollama) "
            "to make that explicit")
    elif cost.allowed(cls, limit):
        add(PASS, "Cost guard", f"brain = {label} ({cls}) · limit = {limit} · "
                                "cannot be charged")
    else:
        add(WARN, "Cost guard", f"brain {label} ({cls}) is above the limit {limit}")


def check_engines() -> None:
    from arcdesk.ai import backends
    found = backends.probe()
    if found:
        names = ", ".join(f"{d.backend.label}"
                          f"{' (' + d.models[0] + ')' if d.models else ''}"
                          for d in found[:4])
        add(PASS, "Local AI engine", names)
    else:
        add(INFO, "Local AI engine",
            "none running — ARC Lite will answer instead (free, no model needed)")
    from arcdesk.ai import catalog
    add(INFO, "Open-source catalogue", f"{len(catalog.CATALOG)} packages · "
                                       "scan: python tools\\github_scan.py --all --plan")


def check_voice() -> None:
    from arcdesk import config
    cfg = config.load()
    wake = cfg.get("wake", {})
    enabled = bool(wake.get("enabled"))

    mic_ok = _module("sounddevice")
    if mic_ok:
        add(PASS, "Microphone library", "sounddevice present")
    else:
        add(WARN if enabled else INFO, "Microphone library",
            "sounddevice missing — pip install -r requirements-voice.txt")

    try:
        engine = "vosk/openwakeword"
        have_vosk = _module("vosk")
        have_oww = _module("openwakeword")
        if have_vosk or have_oww:
            add(PASS, "Wake engine", ", ".join(
                n for n, ok in (("vosk", have_vosk), ("openwakeword", have_oww)) if ok))
        else:
            add(WARN if enabled else INFO, "Wake engine",
                "neither vosk nor openwakeword installed — run install_voice.bat "
                f"({engine})")
    except Exception as exc:
        add(FAIL, "Wake module", f"{type(exc).__name__}: {exc}")

    if enabled and not mic_ok:
        add(FAIL, "Wake word", "enabled in settings but the microphone library is "
                               "missing — it will never hear you")
    elif enabled:
        add(PASS, "Wake word", f'armed for "{wake.get("phrase")}" on port '
                               f'{wake.get("port")}')
    else:
        add(INFO, "Wake word", 'off — turn it on in Settings → Voice → "Listen for '
                               'the wake word"')


def _module(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def check_instance() -> None:
    from arcdesk import config, instance
    cfg = config.load()
    port = instance.lock_port(cfg)
    busy = instance.is_live()
    if busy:
        add(INFO, "Second copy", "this process already holds the lock")
        return
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        add(PASS, "Single-instance lock", f"port {port} free — this copy will be the "
                                         "first")
    except OSError:
        add(WARN, "Single-instance lock",
            f"port {port} busy — Arc Desk is probably already running "
            "(saying the wake word will bring it forward)")
    finally:
        s.close()


def check_build() -> None:
    frozen = bool(getattr(sys, "frozen", False))
    from arcdesk import paths
    if frozen:
        # Not ".exe" hard-coded: the same bundle is built and tested on Linux, and a
        # check that only looks for the Windows name would report a working build as
        # broken. Look for the sibling the daemon is actually called on this platform.
        names = ("ArcDeskVoice.exe", "ArcDeskVoice")
        found = next((n for n in names if (paths.app_dir() / n).exists()), "")
        if found:
            add(PASS, "Packaged build", f"frozen · {found} present next to the window")
        else:
            add(WARN, "Packaged build",
                f"frozen, but {names[0]} is missing next to the window — "
                "the wake word will not work, everything else will")
    else:
        add(INFO, "Packaged build",
            f"running from source at {paths.app_dir()} · build with packaging\\build_all.bat")


def check_desktop_guard() -> None:
    from arcdesk import desktop_guard
    try:
        hits = desktop_guard.scan_sources()
        if not hits:
            add(PASS, "Windows untouched",
                "no wallpaper/taskbar/explorer/icon APIs anywhere in the code")
        else:
            add(WARN, "Windows untouched", f"{len(hits)} hit(s): " + "; ".join(hits[:2]))
    except Exception as exc:
        add(INFO, "Windows untouched", f"scan unavailable here ({type(exc).__name__})")


def check_logs() -> None:
    from arcdesk import logs
    errs = logs.errors(3)
    if errs:
        add(WARN, "Crash log", f"{len(errs)} recent error(s) — see {logs.log_path()}")
        for line in errs:
            print("        " + line[-140:].strip())
    else:
        add(PASS, "Crash log", f"no errors · {logs.log_path()}")


def check_disk() -> None:
    from arcdesk import config
    try:
        usage = shutil.disk_usage(str(config.data_dir()))
        free_gb = usage.free / (1024 ** 3)
        add(PASS if free_gb > 2 else WARN, "Free disk space", f"{free_gb:.1f} GB")
    except Exception:
        add(INFO, "Free disk space", "unknown")


def check_quiet() -> None:
    """Will a command prompt appear behind the app? The one question this answers."""
    try:
        from arcdesk import quiet
        # `covered()` is the honest measure: read from source in a checkout, declared in
        # a compiled build (where there are no .py files to read).
        add(PASS if quiet.covered() else FAIL, "Silent spawns", quiet.describe())
        from arcdesk import logs
        add(PASS, "Console output", logs.describe())
    except Exception as exc:                          # noqa: BLE001
        add(WARN, "Silent spawns", f"could not check: {type(exc).__name__}: {exc}")


CHECKS = (check_python, check_qt, check_config, check_cost, check_engines,
          check_voice, check_instance, check_build, check_desktop_guard,
          check_quiet, check_disk, check_logs)


def run(verbose: bool = True) -> int:
    _rows.clear()
    for fn in CHECKS:
        try:
            fn()
        except Exception as exc:                      # a check must never crash
            add(WARN, fn.__name__.replace("check_", "").title(),
                f"check skipped: {type(exc).__name__}: {exc}")

    if verbose:
        print("Arc Desk · doctor")
        print("=" * 72)
        icons = {PASS: "[ok]  ", WARN: "[warn]", FAIL: "[FAIL]", INFO: "[info]"}
        for status, name, detail in _rows:
            print(f"{icons[status]} {name:<24} {detail}")
        fails = sum(1 for s, _, _ in _rows if s == FAIL)
        warns = sum(1 for s, _, _ in _rows if s == WARN)
        print("=" * 72)
        if fails:
            print(f"RESULT: {fails} problem(s) to fix, {warns} warning(s).")
        elif warns:
            print(f"RESULT: usable, with {warns} warning(s).")
        else:
            print("RESULT: everything checks out.")
    return 1 if any(s == FAIL for s, _, _ in _rows) else 0


def deep(touch: bool = False, as_json: bool = False) -> int:
    """The part a README cannot prove: real desktop tools, real microphone."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from arcdesk import deepcheck

    print("ARC DESK · deep check")
    print("=" * 70)
    print("environment")
    for line in deepcheck.environment():
        print("  " + line)
    print("-" * 70)
    # the pipelines the last waves promised, executed for real, before the desktop
    # tools — if these fail the user does not need to run --touch at all
    rows = deepcheck.run_core() + deepcheck.run_voice() + deepcheck.run_desktop(touch=touch)
    for row in rows:
        print(f"  [{row['verdict']:<6}] {row['tool']:<20} {row.get('detail', '')[:80]}")
    summary = deepcheck.summarise(rows)
    log = deepcheck.write_log(rows, header="mode: " + ("touch" if touch else "safe only"))
    print("-" * 70)
    print(f"ok {summary['ok']} · fail {summary['fail']} · skip {summary['skip']} "
          f"· not attempted {summary['manual']} of {summary['rows']}")
    print(f"log: {log}")
    if not touch:
        print("touch mode (opens Notepad, changes volume, types, locks):")
        print("    python tools\\doctor.py --deep --touch")
    if as_json:
        print(deepcheck.as_json(rows))
    print("RESULT: " + ("failures above" if summary["fail"] else
                        "everything that could run here ran"))
    return 1 if summary["fail"] else 0


def main(argv: list[str] | None = None) -> int:
    if os.name == "nt":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = list(sys.argv[1:] if argv is None else argv)
    if "--deep" in args:
        return deep(touch="--touch" in args, as_json="--json" in args)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
