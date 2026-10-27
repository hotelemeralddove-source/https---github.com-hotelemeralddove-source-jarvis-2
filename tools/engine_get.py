"""One voice engine, installed from a .bat, without a Python traceback.

The report (21.png): `install_clone.bat` offered IndicF5 first, and when Hugging Face
answered **401 — gated repo**, the window filled with forty lines of `transformers`
internals ending in

    OSError: You are trying to access a gated repo …
    (IndicF5 download failed - retry with internet)

Two things are wrong there, and neither is the internet:

  * the model is **gated**: the licence has to be accepted once, and a token supplied.
    Retrying will fail for ever, and the message sent the person looking in the wrong place;
  * a traceback is not an answer. The last line of it is, and the app already knows how to
    say it (`arcdesk.engines.gate()` and `gate_advice()`).

This file is the bridge: the .bat stays a .bat, but every line it prints comes from the same
code the app uses, so the terminal and the dialog can never disagree.

    python tools/engine_get.py auto [ta|hi|en]     download the right one, no questions
    python tools/engine_get.py status              what is installed, one line each
    python tools/engine_get.py gate <engine>       is it gated for us, right now
    python tools/engine_get.py install <engine>    packages, then the weights
    python tools/engine_get.py fetch <engine>      JUST the weights, straight over HTTPS
    python tools/engine_get.py token               where the token comes from, if any
    python tools/engine_get.py token               is a token saved (never prints it)
    python tools/engine_get.py token <value>       save one
    python tools/engine_get.py token --clear       forget it

`auto` is the one install_clone.bat calls: it picks the engine the language needs, shows a
real progress line, and if the model is gated it asks for the token *in the same run* and
carries on downloading. Nobody has to press anything a second time.

Exit codes: 0 done · 1 failed (reason on screen) · 2 needs a token first.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ORDER = ("piper", "xtts", "indicf5")          # smallest / no-token first, by design


def _engines():
    from arcdesk import engines
    return engines


def _say(line: str) -> None:
    print("  " + str(line).rstrip(), flush=True)


class _Live:
    """Print the download as it happens, at most twice a second, on one moving line.

    `engines.read_progress()` turns pip's and huggingface's bars into numbers. In a window
    those numbers go to a QProgressBar; here they have to go somewhere a person can see,
    or the screen looks frozen for the four minutes a 1.9 GB download takes.
    """

    def __init__(self, every: float = 0.5) -> None:
        self.every = every
        self._last = 0.0
        self._drawn = False

    def __call__(self, reading: dict) -> None:
        import time as _t
        now = _t.monotonic()
        done = float(reading.get("percent") or 0)
        if done < 100 and now - self._last < self.every:
            return
        self._last = now
        bits = []
        if reading.get("percent") is not None:
            bits.append(f"{done:5.1f}%")
        if reading.get("mb") is not None:
            total = reading.get("total_mb")
            bits.append(f"{reading['mb']:,.0f} MB" + (f" of {total:,.0f} MB" if total else ""))
        if reading.get("speed"):
            bits.append(str(reading["speed"]))
        eta = str(reading.get("eta") or "").strip()
        if eta and eta.lower() not in ("starting", "0:00", "0"):
            bits.append(eta + " left" if eta.startswith("under") else "about " + eta + " left")
        if not bits:
            return
        sys.stdout.write("\r  … " + " · ".join(bits) + "                    ")
        sys.stdout.flush()
        self._drawn = True
        if done >= 100:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._drawn = False

    def close(self) -> None:
        if self._drawn:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._drawn = False


def _ask_token(engine: str, url: str) -> "str | None":
    """The gate, answered where the person already is: this window.

    Typing the token here is the difference between "download aaga matiku" and a download
    that starts four seconds later. An empty line is a real answer too — it means no.
    """
    from arcdesk import engines
    label = engines.SPECS.get(engine, {}).get("label", engine)
    print()
    print(f"  {label} is a gated model: Hugging Face will not send a single byte until")
    print("  its licence is accepted once. This is not a download problem.")
    print(f"    1. open  {url or 'https://huggingface.co/ai4bharat/IndicF5'}  and click Agree")
    print("    2. make a read token at  https://huggingface.co/settings/tokens")
    print("    3. paste it below — the download continues by itself, in this window.")
    try:
        value = input("  token (or just press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return value or None


def cmd_fetch(engine: str) -> int:
    """Download only the weights, directly, with resume — no libraries involved."""
    engines = _engines()
    if engine not in engines.MODEL_REPO:
        print(f"  unknown engine {engine!r} — pick one of: {', '.join(ORDER)}")
        return 1
    live = _Live()
    got = engines.fetch(engine, on_line=_say, on_progress=live)
    live.close()
    if got.get("ok"):
        print(f"\n  the files are in place: {got.get('path')}")
        print("  a normal install (engine_get.py install) now finds them and skips the "
              "download.")
        return 0
    if got.get("needs_token"):
        print("\n  Hugging Face refused the files, so they need a token.")
        print(engines.gate_advice(engine))
        return 2
    print(f"\n  the download stopped: {got.get('why')}")
    print("  running this again resumes from the files that already arrived.")
    return 1


def cmd_auto(lang: str) -> int:
    """One command, no questions, no second press: the download of the right engine."""
    from arcdesk import engines
    wanted = engines.pick(lang)
    state = engines.status().get(wanted, {})
    if state.get("ready"):
        # "through the terminal all engines downloaded … but ipo kanom": the installer
        # must not start a 1.5 GB download over an engine that is already here.
        print(f"  {state['label']} is already on this PC and ready — nothing to download.")
        if state.get("python"):
            print(f"  JARVIS speaks through: {state['python']}")
        return 0
    if state.get("code"):
        print(f"  {state['label']} is installed here — only the weights are missing, so "
              f"only those are downloaded.")
    live = _Live()
    got = engines.auto("", lang=lang, on_line=_say, on_progress=live,
                       ask_token=_ask_token)
    live.close()
    if got.get("ok"):
        print()
        print(f"  ready. Next: teach it YOUR voice —")
        print(f'    {sys.executable} tools\\voice_setup.py import "C:\\path\\to\\your-clip.mp4"')
        return 0
    if got.get("needs_space"):
        print()
        print(f"  {got.get('why')}")
        print("  Nothing was downloaded, so nothing was wasted. Free the space and run this "
              "again.")
        return 1
    if got.get("needs_token"):
        print()
        print("  no token, so nothing was downloaded — that is a decision, not a failure.")
        print("  Piper (~60 MB, no account) can speak English and Hindi today:")
        print(f"    {sys.executable} tools\\engine_get.py install piper")
        return 2
    print()
    print(f"  could not finish: {got.get('why') or 'unknown reason'}")
    for line in [ln for ln in (got.get("lines") or []) if ln.strip()][-3:]:
        print("    " + line.strip())
    return 1


def cmd_status() -> int:
    engines = _engines()
    st = engines.status()
    print("what this computer can speak with:")
    for key in ORDER:
        row = st.get(key)
        if not row:
            continue
        note = ""
        if row["ready"]:
            mark = "ready"
        elif row.get("code"):
            # the half-installed state that used to read "not installed" and send the
            # person round the same loop they had already finished
            mark = "engine found"
            note = row.get("problem") or "partly installed"
        elif row.get("problem") == "gated model — needs a token":
            mark = "needs a token"
        else:
            mark = "not installed"
        print(f"  {row['label']:<10} {row['langs']:<18} {mark:<16} "
              f"{row['size_mb']:>5} MB")
        if note:
            print(f"  {'':<10} only this is left: {note}")
        if row.get("python"):
            print(f"  {'':<10} installed in: {row['python']}")
    tok, where = engines.token_source()
    print(f"\n  huggingface token: " + (f"found — {where}" if tok
                                       else "none  (only gated models need one)"))
    for key in ORDER:
        local = st.get(key, {}).get("local") or ""
        if local:
            print(f"  {st[key]['label']} weights: already on this PC — {local}")
    if engines.SPECS["piper"]["size_mb"] <= 120:
        print("  piper is the small one: ~60 MB, no account, no GPU.")
    ready = [row["label"] for row in st.values() if row["ready"]]
    half = [f"{row['label']} ({row['problem']})" for row in st.values()
            if row.get("code") and not row["ready"]]
    print()
    if ready:
        print("  verdict: JARVIS can speak in a cloned voice with " + ", ".join(ready) + ".")
    else:
        print("  verdict: no clone engine can speak yet — replies use the system voice.")
    for item in half:
        print(f"  only the missing part is left for {item}: the app downloads that alone "
              f"(Settings → Voice), nothing you installed is touched.")
    return 0


def cmd_gate(engine: str) -> int:
    engines = _engines()
    state = engines.gate(engine)
    if state.get("gated"):
        print(f"{engine} is GATED — Hugging Face refuses it (401) until the licence is "
              f"accepted once.")
        print(engines.gate_advice(engine))
        return 2
    if state.get("unknown"):
        print(f"  could not reach Hugging Face to check {engine} — trying anyway")
        return 0
    print(f"  {engine}: no licence needed")
    return 0


def cmd_token(argv: list[str]) -> int:
    engines = _engines()
    if not argv:
        have = engines.token()
        print("  a token is saved" if have else "  no token saved yet")
        if have:
            print("  (it is never printed back — paste a new one to replace it)")
        return 0
    if argv[0] in ("--clear", "clear", "-"):
        engines.set_token("")
        print("  token cleared")
        return 0
    engines.set_token(argv[0])
    print("  token saved — it is kept in the app's own settings, never in a file here")
    return 0


class _Reporter:
    """Write what is happening into a small JSON file the app can read.

    The window and this script are separate processes on purpose (see
    `arcdesk/engine_helper.py`): the download has to survive the window. That only works if
    the window can *see* it, which is this file. Written atomically, so a reader never sees
    half a snapshot, and it carries the last lines of the log so the app can show real
    output instead of a spinner.
    """

    def __init__(self, path: str, engine: str) -> None:
        self.path = Path(path) if path else None
        self.engine = engine
        self.lines: list[str] = []
        self.stage = "starting"
        self.reading: dict = {"percent": 0.0, "mb": 0.0, "total_mb": 0.0,
                              "speed": "", "eta": ""}
        self.done = False
        self.why = ""
        self._last = 0.0

    def line(self, text: str) -> None:
        text = str(text).strip()
        if text:
            self.lines.append(text)
            self.lines = self.lines[-12:]
            if not text[:1].isdigit():
                self.stage = text[:120]
        self.write()

    def progress(self, reading: dict) -> None:
        self.reading.update({k: v for k, v in reading.items() if k != "line"})
        self.write(throttle=0.4)

    def finish(self, ok: bool, why: str = "") -> None:
        self.done = True
        self.why = why
        self.stage = "done" if ok else (why or "failed")
        self.write()

    def write(self, throttle: float = 0.0) -> None:
        if self.path is None:
            return
        import time as _t
        now = _t.monotonic()
        if throttle and now - self._last < throttle:
            return
        self._last = now
        import json
        import os as _os
        payload = {
            "pid": _os.getpid(),
            "engine": self.engine,
            "stage": self.stage,
            "percent": float(self.reading.get("percent") or 0.0),
            "mb": self.reading.get("mb") or 0.0,
            "total_mb": self.reading.get("total_mb") or 0.0,
            "speed": self.reading.get("speed") or "",
            "eta": self.reading.get("eta") or "",
            "done": self.done,
            "why": self.why,
            "ok": bool(self.done and not self.why),
            "lines": self.lines[-6:],
            "updated": _t.strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:                                        # noqa: BLE001
            pass


def _cancel_requested(engine: str) -> str:
    """The app asks for a stop by writing a file next to the progress file."""
    try:
        from arcdesk import engine_helper
        path = engine_helper.cancel_path(engine)
        return "cancelled" if path.exists() else ""
    except Exception:                                            # noqa: BLE001
        return ""


def cmd_install(engine: str, progress_file: str = "", lang: str = "") -> int:
    """Install one named engine — the same code path the app's button uses.

    `engines.auto` is what makes this a download rather than a message: a gated model is
    paused for the token here, in this window, and then carries on by itself.
    """
    engines = _engines()
    if engine not in engines.SPECS:
        print(f"  unknown engine {engine!r} — pick one of: {', '.join(ORDER)}")
        return 1
    spec = engines.SPECS[engine]
    state = engines.status().get(engine, {})
    if state.get("ready"):
        print(f"  {spec['label']} is already on this PC and ready — nothing to download.")
        if state.get("python"):
            print(f"  JARVIS speaks through: {state['python']}")
        return 0
    half = bool(state.get("code"))
    print(("finishing " if half else "installing ") +
          f"{spec['label']} ({spec['langs']}) — about "
          f"{spec['size_mb'] / 1000:.1f} GB, once. Ctrl+C stops it.")
    if half:
        print(f"  the packages are already here ({state.get('python') or 'this PC'}), so "
              f"only {state.get('problem') or 'the missing part'} is downloaded.")
    live = _Live()
    report = _Reporter(progress_file, engine)
    report.line(f"{'finishing' if half else 'installing'} {spec['label']} — about "
                f"{spec['size_mb'] / 1000:.1f} GB")

    import threading as _threading
    stop_flag = _threading.Event()

    def watch_cancel() -> None:
        """Poll the app's stop file; the engines code takes the same cancel Event."""
        while not stop_flag.wait(1.0):
            if _cancel_requested(engine):
                stop_flag.set()
                return

    _threading.Thread(target=watch_cancel, name="arc-helper-cancel", daemon=True).start()

    def say_both(text: str) -> None:
        _say(text)
        report.line(text)

    def progress_both(reading: dict) -> None:
        live(reading)
        report.progress(reading)

    try:
        if half:
            got = engines.missing_only(engine, on_line=say_both, on_progress=progress_both,
                                       cancel=stop_flag)
            if got.get("ok"):
                from arcdesk import clone
                clone.refresh()
            else:
                got = dict(got, engine=engine)
        else:
            got = engines.auto(engine=engine, on_line=say_both, on_progress=progress_both,
                               ask_token=_ask_token, cancel=stop_flag)
    except KeyboardInterrupt:
        live.close()
        print("\n  stopped by you. Nothing half-installed is used; run this again any time.")
        return 1
    except Exception as exc:                                     # noqa: BLE001
        live.close()
        # One line, never a traceback: the last line of a traceback is the only part a
        # person can act on, and it is already in `exc`.
        print(f"\n  {spec['label']} could not be installed: {type(exc).__name__}: {exc}")
        print("  the app says the same thing in Settings → Voice, with a retry button.")
        return 1
    live.close()
    report.finish(bool(got.get("ok")), "" if got.get("ok") else str(got.get("why") or ""))
    return _report(engine, got)


def _report(engine: str, got: dict) -> int:
    """Turn one finished run into an exit code and a line a person can act on."""
    from arcdesk import engines
    spec = engines.SPECS.get(engine, {"label": engine})
    if got.get("ok"):
        print(f"\n  {spec['label']} is ready. Next: teach it YOUR voice —")
        print(f'    {sys.executable} tools\\voice_setup.py import "C:\\path\\to\\your-clip.mp4"')
        return 0
    if got.get("needs_space"):
        print(f"\n  {got.get('why')}")
        print("  Nothing was downloaded, so nothing was wasted.")
        return 1
    if got.get("needs_token"):
        print("\n  nothing was downloaded, and nothing will be until the licence is "
              "accepted.")
        print(engines.gate_advice(engine))
        return 2
    if got.get("why") == "cancelled":
        print("\n  stopped by you. Nothing half-installed is used; run this again any time.")
        return 1
    print(f"\n  {spec['label']} is NOT ready: {got.get('why') or 'unknown reason'}")
    if got.get("needs_token"):
        print(engines.gate_advice(engine))
        return 2
    for line in [ln for ln in (got.get("lines") or []) if ln.strip()][-3:]:
        print("    " + line.strip())
    print("  the same run is in Settings → Voice, where it can be retried with a button.")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__.split("Exit codes")[0].strip())
        return 0
    what, rest = argv[1], argv[2:]
    try:
        if what == "status":
            return cmd_status()
        if what == "gate":
            return cmd_gate(rest[0] if rest else "indicf5")
        if what == "token":
            return cmd_token(rest)
        if what == "install":
            engine = rest[0] if rest else "piper"
            progress_file, lang = "", ""
            if "--progress-file" in rest:
                progress_file = rest[rest.index("--progress-file") + 1]
            if "--lang" in rest:
                lang = rest[rest.index("--lang") + 1]
            return cmd_install(engine, progress_file=progress_file, lang=lang)
        if what == "auto":
            return cmd_auto(rest[0] if rest else "ta")
        if what == "fetch":
            return cmd_fetch(rest[0] if rest else "xtts")
    except Exception as exc:                                    # noqa: BLE001
        print(f"  could not do that: {type(exc).__name__}: {exc}")
        return 1
    print(f"  unknown command {what!r} — try: status / gate / install / token")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
