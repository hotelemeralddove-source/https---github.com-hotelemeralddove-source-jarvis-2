"""The ears — microphone library, wake engine, and the two models. Checked, then fixed.

The user's report was *"voice commandku no respond"*, and the setup card had already
half-said why in small grey text: *"sounddevice is installed but no wake-word engine is
(openwakeword or vosk)"*. A sentence in grey at the bottom of a card is not a fix.

Three separate things have to be true before "hey jarvis" can work, and they fail for
three different reasons:

    microphone library   sounddevice (bundled) or pyaudio        — pip
    wake engine          vosk or openwakeword                    — pip
    the speech model     40 MB Vosk model in the data folder     — a download
    the speaker model    30 MB, only for the voice lock          — a download

`status()` names each one and what is missing; `fix()` does what can be done from inside
the app, streaming its progress, and then **re-checks** instead of assuming. On a frozen
build the two Python packages cannot be added after the fact (they are compiled into the
exe), so that case is reported in one plain sentence rather than a spinner.
"""
from __future__ import annotations

import threading
from typing import Callable

from . import config

Line = Callable[[str], None]


def _have(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def model_dir():
    """Where the 40 MB Vosk model really is — one list, shared with the setup card."""
    from .widgets.voice_ready import model_dir as _md
    return _md()


def speaker_model():
    p = config.data_dir() / "models" / "speaker_embedding.onnx"
    return p if p.exists() and p.stat().st_size > 1_000_000 else None


def status() -> dict:
    """Every requirement, on its own, with the size of the fix."""
    from .widgets.voice_ready import engine, mic_backend
    mic = mic_backend()
    eng = engine()
    model = model_dir()
    spk = speaker_model()
    rows = {
        "mic": {"ok": bool(mic), "label": "microphone library", "found": mic,
                "fix": "pip", "size_mb": 3, "need": "sounddevice"},
        "engine": {"ok": bool(eng), "label": "wake-word engine", "found": eng,
                   "fix": "pip", "size_mb": 8, "need": "vosk"},
        "model": {"ok": bool(model), "label": "speech model (40 MB)",
                  "found": str(model) if model else "", "fix": "download", "size_mb": 40,
                  "need": "vosk-model-small-en-us-0.15"},
        "speaker": {"ok": bool(spk), "label": "speaker model — voice lock (30 MB)",
                    "found": str(spk) if spk else "", "fix": "download", "size_mb": 30,
                    "need": "speaker_embedding.onnx"},
    }
    missing = [k for k, v in rows.items() if not v["ok"]]
    can_hear = all(rows[k]["ok"] for k in ("mic", "engine", "model"))
    return {
        "rows": rows,
        "missing": missing,
        "ready": can_hear,
        "wake_possible": can_hear,
        "sentence": sentence(rows, can_hear),
        "pip_possible": pods(),
    }


def pods() -> bool:
    """Can this build add a Python package after the fact? (frozen = no)"""
    try:
        from . import engines
        m = engines.method()
        return bool(m.get("can_install") and not m.get("frozen"))
    except Exception:
        return False


def sentence(rows: dict, can_hear: bool) -> str:
    if can_hear:
        return (f"Ears ready: {rows['mic']['found']} + {rows['engine']['found']}, "
                f"speech model on disk.")
    bits = []
    if not rows["mic"]["ok"]:
        bits.append("no microphone library")
    if not rows["engine"]["ok"]:
        bits.append("no wake-word engine (vosk)")
    if not rows["model"]["ok"]:
        bits.append("speech model not downloaded")
    return "Cannot listen yet — " + ", ".join(bits) + "."


# --------------------------------------------------------------------------- fixing
def _download_models(on_line: Line, cancel: threading.Event | None) -> bool:
    """The 40 MB speech model + the 30 MB speaker model. No pip involved."""
    from . import paths, voiceid
    from .engines import _run

    ok_all = True
    if model_dir() is None:
        on_line("speech model: ~40 MB from alphacephei.com (the Vosk model)")
        try:
            cmd, kwargs = paths.daemon_command(8765, "hey jarvis", "auto", "bye jarvis",
                                               extra=["--download-model"])
        except Exception as exc:                                # noqa: BLE001
            on_line(f"could not build the download command: {exc}")
            return False
        got = _run(cmd, on_line, cancel)
        ok_all &= bool(got["ok"])
        if not got["ok"]:
            on_line("speech model did not arrive — check the internet connection")
    else:
        on_line("speech model: already on disk")

    if speaker_model() is None:
        on_line("speaker model: ~30 MB (only used by the voice lock)")
        try:
            res = voiceid.download_model()
            on_line("  " + str(res.get("message", ""))[:160])
            ok_all &= bool(res.get("ok"))
        except Exception as exc:                                # noqa: BLE001
            on_line(f"  speaker model failed: {exc}")
            ok_all = False
    else:
        on_line("speaker model: already on disk")
    return ok_all


def _pip_install(on_line: Line, cancel: threading.Event | None) -> bool:
    import sys
    from .engines import _run
    got = _run([sys.executable, "-m", "pip", "install", "vosk", "sounddevice"],
               on_line, cancel)
    return bool(got["ok"])


def fix(on_line: Line | None = None, cancel: threading.Event | None = None) -> dict:
    """Do everything that can be done from in here, then check again — honestly."""
    say: Line = on_line or (lambda _l: None)
    before = status()
    say(before["sentence"])
    if before["ready"] and not before["rows"]["speaker"]["ok"]:
        say("the ears work; only the voice lock's speaker model is missing")

    if not before["rows"]["mic"]["ok"] or not before["rows"]["engine"]["ok"]:
        if pods():
            say("step 1 of 2 · installing vosk + sounddevice (needs internet, ~11 MB)")
            _pip_install(say, cancel)
        else:
            say("this build already contains the microphone code, so the missing piece "
                "is only the models — continuing")
    if cancel is not None and cancel.is_set():
        return {"ok": False, "why": "cancelled", "status": status()}

    say("step 2 of 2 · the models")
    _download_models(say, cancel)
    if cancel is not None and cancel.is_set():
        return {"ok": False, "why": "cancelled", "status": status()}

    after = status()
    say(after["sentence"])
    if after["ready"]:
        say("say \"hey jarvis\" — Settings → Voice has the wake test if you want to see it "
            "work without speaking.")
    else:
        still = [after["rows"][k]["label"] for k in after["missing"]]
        say("still missing: " + ", ".join(still) + ". Nothing here will pretend to listen.")
    return {"ok": after["ready"], "why": "" if after["ready"] else
            "still missing " + ", ".join(after["missing"]), "status": after}
