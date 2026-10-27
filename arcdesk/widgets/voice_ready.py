"""Can this machine actually hear? — asked before anything promises to listen.

A "yes" here has to mean all four of these, and it is cheap to check:

    sounddevice (or pyaudio)   something to read the microphone
    vosk or openwakeword       something to recognise the wake phrase
    a model (for vosk)         the 40 MB speech model, if Vosk is the engine

The wizard, Settings and the doctor all use this one function, so the app can never say
"listening" in one place and "not installed" in another.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _have(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def mic_backend() -> str:
    for name in ("sounddevice", "pyaudio"):
        if _have(name):
            return name
    return ""


def engine() -> str:
    for name in ("openwakeword", "vosk"):
        if _have(name):
            return name
    return ""


VOSK_MODEL = "vosk-model-small-en-us-0.15"


def _looks_like_a_model(path: Path) -> bool:
    """A folder that Vosk can actually open, not just a folder with a name we like.

    A real Vosk model has an `am/` (or `am_final/`) directory with the acoustic model in
    it. Checking the name alone is how a half-finished download counts as "ready" and the
    first "hey jarvis" then fails.
    """
    try:
        if not path.is_dir() or not any(path.iterdir()):
            return False
        # the real layout: am/ + conf/ (+ graph/, ivector/). Nothing nested, so a folder
        # that merely CONTAINS a model does not count as one.
        return (path / "am").is_dir() or (path / "am_final").is_dir() \
            or (path / "conf").is_dir()
    except Exception:
        return False


def model_candidates() -> list[Path]:
    """Every place this model is known to be written, in the order it was added.

    The bug this exists for: `arc_daemon.py --download-model` unpacks the model to
    `<data>/vosk-model-small-en-us-0.15`, and this function used to look only in
    `<data>/models/vosk` and `<data>/vosk-model`. So the download said
    "[arc-voice] already present: …\\vosk-model-small-en-us-0.15" and the very next line
    said "speech model not downloaded" — the user's screenshot, exactly. One list, one
    place, used by the ears dialog, the setup card and the doctor.
    """
    from .. import config
    data = config.data_dir()
    out = [data / VOSK_MODEL,
           data / "models" / VOSK_MODEL,
           data / "models" / "vosk",
           data / "vosk-model"]
    # anything else of the shape vosk-model-* the user may have unpacked by hand
    try:
        out += sorted(p for p in data.glob("vosk-model*") if p.is_dir())
        out += sorted(p for p in (data / "models").glob("vosk-model*") if p.is_dir())
    except Exception:
        pass
    out.append(Path.home() / ".cache" / "arcdesk" / "vosk")
    seen, unique = set(), []
    for p in out:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def model_dir() -> Path | None:
    for candidate in model_candidates():
        if _looks_like_a_model(candidate):
            return candidate
    return None


def can_listen() -> tuple[bool, str]:
    """(True, what is available) or (False, the one sentence that says what to install)."""
    mic = mic_backend()
    eng = engine()
    if not mic and not eng:
        return False, ("no microphone library yet — run install_voice.bat "
                       "(installs sounddevice + vosk + the 40 MB model)")
    if not mic:
        return False, f"{eng} is installed but no mic library is (sounddevice/pyaudio)"
    if not eng:
        return False, (f"{mic} is installed but no wake-word engine is "
                       f"(openwakeword or vosk)")
    if eng == "vosk" and model_dir() is None:
        return False, ("vosk is installed but the speech model is not — run "
                       "python arc_daemon.py --download-model")
    return True, f"{mic} + {eng}"
