"""Piper, without ever loading Piper into the app's own process.

The report: "piper and innoru voice tool install pananum then application auto close
aaguthu". Piper is `piper-tts`, which pulls `onnxruntime` — a native library with its own
OpenMP/MKL DLLs. A Qt app that already has its own DLLs loaded can die on that import
with **no traceback at all**: Windows terminates the process (OMP: Error #15, then abort)
and the window just disappears. Nothing is caught, nothing is logged, so it looks like the
app closing itself.

So the rule since fix41 is: **`import piper` never happens in the app's process.** Asking
"is it installed?" uses `importlib.util.find_spec`, which looks at the file system and
executes nothing. Speaking runs piper in a short-lived child process; if that child dies,
the app only loses a sentence and falls back to the next voice, which is fine.

Which interpreter? The app's private engine folder first (that is where the Install button
puts things), then anything else on the PC that already has piper — including the python
someone installed it into from a terminal.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from . import quiet

CACHE_SECONDS = 600.0
_CACHE: dict = {"at": 0.0, "python": ""}

#: One sentence, one child process. Kept tiny on purpose: no app imports, no logging, and
#: a non-zero exit if anything at all goes wrong.
_SCRIPT = """
import sys, wave
voice_path, out, text = sys.argv[1], sys.argv[2], sys.argv[3]
length = float(sys.argv[4])
from piper import PiperVoice, SynthesisConfig
voice = PiperVoice.load(voice_path)
cfg = SynthesisConfig(length_scale=length)
with wave.open(out, "wb") as wf:
    voice.synthesize_wav(text, wf, syn_config=cfg)
print("PIPER-OK")
"""


def _has_piper(exe: str) -> bool:
    """Does that interpreter have piper? find_spec only — nothing is imported."""
    code = ("import importlib.util,sys;"
            "sys.exit(0 if importlib.util.find_spec('piper') else 1)")
    try:
        got = quiet.run([exe, "-c", code], capture_output=True, text=True, timeout=20)
        return got.returncode == 0
    except Exception:                                            # noqa: BLE001
        return False


def python_with_piper(refresh: bool = False) -> str:
    """An interpreter that can speak with piper ('' if none). Cached: this starts a child.

    Order: the app's private engine folder (what the Install button fills), then this
    process, then anything else on the PC — so a terminal `pip install piper-tts` is
    used, not asked for again.
    """
    now = time.monotonic()
    if not refresh and (now - _CACHE["at"]) < CACHE_SECONDS:
        return str(_CACHE["python"])
    found = ""
    try:
        from . import engines
        first = [engines.sidecar_python(), Path(sys.executable)]
        for exe in first:
            try:
                if Path(exe).exists() and _has_piper(str(exe)):
                    found = str(exe)
                    break
            except Exception:                                    # noqa: BLE001
                continue
        if not found:
            for _label, exe in engines.interpreters():
                if _has_piper(exe):
                    found = exe
                    break
    except Exception:                                            # noqa: BLE001
        found = ""
    _CACHE.update(at=now, python=found)
    return found


def refresh() -> None:
    _CACHE.update(at=0.0, python="")


def known_python() -> str:
    """The cached answer only — no child process, safe to call on the speaking path.

    Starting a python to ask a question costs ~50-150 ms, and "which voice speaks this
    sentence" runs constantly. So `piper_available()` uses this and a cheap file check,
    and the real search happens at speak time or from `discover_async()`.
    """
    return str(_CACHE["python"])


def discover_async(delay: float = 2.0) -> None:
    """Look for piper in the background, a moment later. Never blocks a sentence.

    The short sleep is deliberate: this is kicked off by the first "can piper speak?"
    check, which happens while the app is busy putting a reply together. Starting child
    processes in the same millisecond would make that reply slower for no reason.
    """
    import threading

    def look() -> None:
        import time as _time
        _time.sleep(max(0.0, delay))
        try:
            python_with_piper(refresh=True)
        except Exception:                                        # noqa: BLE001
            pass

    threading.Thread(target=look, name="arc-piper-discover", daemon=True).start()


def available() -> bool:
    """True when some interpreter can do it — never imports piper here."""
    return bool(python_with_piper())


def speak(text: str, voice_path: str, out_wav: str, length_scale: float = 1.0,
          python: str = "") -> dict:
    """Synthesize one sentence into `out_wav` in a child process.

    Returns {"ok", "why"}. ok never means "the app can import piper" — it means a wav
    exists on disk. A crash in the child is a failed sentence, not a dead app.
    """
    exe = python or python_with_piper()
    if not exe:
        return {"ok": False, "why": "no interpreter on this PC has piper"}
    if not Path(voice_path).exists():
        return {"ok": False, "why": f"the piper voice file is missing: {voice_path}"}
    out = Path(out_wav)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        try:
            out.unlink()
        except OSError:
            pass
    try:
        got = quiet.run([exe, "-c", _SCRIPT, str(voice_path), str(out), text,
                         str(max(0.5, min(float(length_scale), 2.0)))],
                        capture_output=True, text=True, timeout=240)
    except Exception as exc:                                     # noqa: BLE001
        return {"ok": False, "why": f"could not start piper: {type(exc).__name__}"}
    if got.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
        last = ((got.stderr or got.stdout or "").strip().splitlines() or [""])[-1]
        return {"ok": False, "why": f"piper could not speak (exit {got.returncode}): "
                                    f"{last[:160]}"}
    return {"ok": True, "why": ""}


def diagnose() -> str:
    """One honest paragraph for the log box under the engine buttons."""
    exe = python_with_piper(refresh=True)
    if exe:
        return f"piper is installed in: {exe}\n  (speaking runs there, in a child process)"
    try:
        from . import engines
        rows = engines.diagnose()["interpreters"]
    except Exception:                                            # noqa: BLE001
        rows = []
    lines = ["no interpreter on this PC has piper yet. checked:"]
    lines += [f"  {r['label']:<16} {r['python']}  has: {', '.join(r['has']) or 'nothing'}"
              for r in rows]
    return "\n".join(lines)
