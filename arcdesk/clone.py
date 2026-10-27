"""Your voice, saying JARVIS's words — the honest version.

The ask: *"naan enna language-la pesunalum, reply antha language-la varanum, aana
voice naan upload panna clip-oda voice-la irukanum."* That is **zero-shot voice
cloning**: give a model 5-20 seconds of a voice plus its transcript, and it speaks
new text in that voice.

What it takes, and what this file refuses to pretend:

| | engine | clones? | languages | licence | runs on |
|---|---|---|---|---|---|
| Indic language reply | **IndicF5** (AI4Bharat, 330M) | yes | 11 Indic: ta, hi, kn, te, ml, bn, gu, mr, pa, or, as | code MIT; weights: clone only voices you have permission for | GPU strongly recommended |
| English / other | **XTTS-v2** (Coqui) | yes | 17, incl. hi — **no Tamil** | CPML: personal / non-commercial only | CPU possible, slow |
| no clone engine | **Piper** | no | many, incl. ta | GPL-3.0 fork | CPU, fast |
| nothing installed | **Windows SAPI** | no | whatever Windows has | OS | instant |

Three consequences, stated plainly instead of discovered later:

1. **Tamil + your cloned voice needs IndicF5.** XTTS cannot pronounce Tamil at all,
   and Chatterbox (MIT) does not tokenise Tamil either. If IndicF5 is not installed,
   ARC says so and speaks Tamil in a Piper voice — a different voice, but real Tamil.
   It does **not** silently play your English voice mispronouncing Tamil.
2. **Cloning is a model, not a setting.** Nothing here downloads 1-2 GB behind your
   back. `install_clone.bat` does it once, visibly, and `plan()` always reports what
   is actually on the machine.
3. **A 12-second clip with music in it clones the music too.** `import_reference()`
   trims to the best continuous speech, normalises loudness, resamples to 24 kHz
   mono, and keeps the transcript on disk, because IndicF5 needs it.

Nothing in this module is allowed to raise into the speech thread: `speak()` returns
False when it cannot do the job, and the caller falls back down the chain.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from . import audio, quiet
import sys
import wave
from pathlib import Path

# Languages each engine can actually pronounce. Kept as data, not prose, so the
# routing can be tested. Codes are the ones `lang.py` already produces.
INDIC_LANGS = ("ta", "hi", "kn", "te", "ml", "bn", "gu", "mr", "pa", "or", "as")
XTTS_LANGS = ("en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs",
              "ar", "zh", "ja", "hu", "ko", "hi")
PIPER_LANGS = INDIC_LANGS + XTTS_LANGS          # voices exist for most of these

# THE CONTRACT: three languages are promised and tested. Everything else in
# INDIC_LANGS / XTTS_LANGS is a bonus that may work, and is never claimed.
PROMISED = {
    "ta": ("indicf5", "Tamil"),
    "hi": ("indicf5", "Hindi"),
    "en": ("xtts", "English"),
}
PROMISED_CODES = tuple(PROMISED)

SAMPLE_RATE = 24000          # what both cloning engines want to hear
MIN_SECONDS = 4.0            # shorter than this and the clone sounds like a stranger
IDEAL_SECONDS = 12.0


# --------------------------------------------------------------------- paths
def voice_dir() -> Path:
    from . import config
    d = config.data_dir() / "voice"
    d.mkdir(parents=True, exist_ok=True)
    return d


def reference() -> Path | None:
    """The clip JARVIS clones, if one has been imported."""
    p = voice_dir() / "reference.wav"
    return p if p.exists() else None


def transcript() -> str:
    t = voice_dir() / "reference.txt"
    return t.read_text(encoding="utf-8").strip() if t.exists() else ""


def _set_transcript(text: str) -> None:
    (voice_dir() / "reference.txt").write_text((text or "").strip() + "\n", encoding="utf-8")


# ------------------------------------------------------------------- engines
def _model_dir(name: str) -> Path | None:
    """Where a Hugging Face model already is on this PC, or None. Never downloads.

    Two things this must not get wrong, both measured:

      * **an empty folder is not a model.** `models--ai4bharat--IndicF5/snapshots` can
        exist with nothing in it (a gated download that stopped at the first file), and
        the old check took its existence as "weights are here" — so the app offered the
        engine, then failed to speak. Weights are big files; this looks for one.
      * **folder names are case-insensitive on Windows and not on Linux.** The cache
        spells the repo `models--coqui--XTTS-v2` while the code asks for `xtts_v2`, which
        matched on Windows and never on Linux. The comparison is lowercased so both
        platforms answer the same.
    """
    env = os.getenv("ARCDESK_MODELS", "").strip()
    home = Path.home()
    # ARCDESK_MODELS means "look only here" — that is what a test needs to be able to
    # answer the same way on a machine that happens to have a model already.
    roots = ([Path(env)] if env else
             [home / ".cache" / "huggingface" / "hub", home / ".cache" / "arcdesk" / "models"])
    # `xtts_v2` vs `models--coqui--XTTS-v2`: underscores, hyphens and case all differ
    # between what the code calls a model and what the cache calls a folder, so the
    # comparison is made on letters and digits alone.
    def flat(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    want = flat(name)
    for root in roots:
        try:
            if not root.exists():
                continue
            for cand in sorted(root.iterdir()):
                if not cand.is_dir() or want not in flat(cand.name):
                    continue
                if _has_weights(cand):
                    return cand
        except Exception:                                        # noqa: BLE001
            continue
    return None


def _has_weights(folder: Path) -> bool:
    """A model folder only counts if a real weight file is inside it."""
    try:
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in (".safetensors", ".pth", ".bin",
                                                          ".onnx", ".ckpt"):
                if path.stat().st_size > 1_000_000:
                    return True
    except Exception:                                            # noqa: BLE001
        return False
    return False


_CACHE: dict = {"at": 0.0, "data": None}
CACHE_SECONDS = 30.0


def refresh() -> None:
    """Forget the cached probe — call after installing or removing an engine."""
    _CACHE["at"] = 0.0
    _CACHE["data"] = None


def engines(cached_only: bool = False) -> dict[str, dict]:
    """What is installed right now. Never imports a heavy module just to check.

    Cached for `CACHE_SECONDS` on purpose: `route()` runs on every spoken sentence,
    and importing `transformers` to answer "is it there?" takes seconds. Probing a
    model cache is cheap; importing the model is not.

    `cached_only=True` is for the drawing thread: a cold cache then means "say nothing
    new", never "ask every python on this PC what it has, on the paint clock". The
    status card ticks every 10 s and the probe takes minutes on a machine that already
    has the engine — that combination was the "settings (Not Responding)" report.
    """
    import time as _time
    now = _time.monotonic()
    if _CACHE["data"] is not None and (now - _CACHE["at"]) < CACHE_SECONDS:
        return _CACHE["data"]
    if cached_only:
        return dict(_CACHE["data"] or {})
    out: dict[str, dict] = {}
    for key, module, model in (("indicf5", "transformers", "IndicF5"),
                               ("xtts", "TTS", "xtts_v2")):
        model_path = _model_dir(model)
        # "I installed it in a terminal but JARVIS asks again" — and its meaner cousin,
        # "engines downloaded, but nothing shows": the packages can be in a different
        # interpreter than this process (a conda env, another venv). That interpreter is
        # asked FIRST, and it is asked even when the weights are not here yet, because
        # "code found, only the 1.5 GB weights missing" is a different sentence — and a
        # different button — from "nothing is installed".
        other = _foreign_python(key)
        code = _importable(module) or bool(other)
        out[key] = {
            "available": bool(model_path) and code,
            "code": code,
            "module": module,
            "model": str(model_path) if model_path else "",
            "foreign": other,
            "why": "",
        }
        if not out[key]["available"]:
            missing = []
            if not model_path:
                missing.append(f"the {model} weights")
            if not code:
                missing.append(f"the '{module}' package")
            out[key]["why"] = "missing " + " and ".join(missing)
    # The installed .exe keeps its engine in a private folder (see engines.py), so a
    # missing local package can still mean "ready" — but only when that folder really
    # has the weights, and the reply is then produced by a child process.
    try:
        from . import engines as _engmod
        for key in ("indicf5", "xtts"):
            if not out[key]["available"] and _engmod.sidecar_ready(key):
                out[key].update(available=True, sidecar=True, model=str(_engmod.sidecar_dir()),
                                why="")
    except Exception:
        pass

    # Piper has the same two halves as the others, and they were being added together:
    # the *engine* is a pip package, the *voice* is a separate .onnx file. A terminal
    # `pip install piper-tts` therefore arrived as "piper is not installed" — true and
    # useless — and the person was told to install what they had just installed.
    piper_python, piper_voices = _piper_parts()
    piper_ok = bool(piper_python) and piper_voices > 0
    out["piper"] = {"available": piper_ok, "code": bool(piper_python), "module": "piper",
                    "model": "", "foreign": piper_python, "voices": piper_voices,
                    "why": "" if piper_ok else
                    ("the piper engine" if not piper_python else
                     ("a piper voice (.onnx, ~30 MB, one per language)"
                      if not piper_voices else "piper"))}
    _CACHE["data"] = out
    _CACHE["at"] = now
    return out


def _foreign_python(key: str) -> str:
    """A python on this PC that already has this engine's packages ('' if none).

    Cached with the rest of the probe: this starts a child process, so it must not run on
    every spoken sentence. When `ARCDESK_NO_FOREIGN_PYTHON` is set (tests), it never runs.
    """
    if os.environ.get("ARCDESK_NO_FOREIGN_PYTHON"):
        return ""
    try:
        from . import engines as _engmod
        # CACHED ONLY. This is asked while a dialog is being built; measuring it means
        # starting child python processes, which froze Settings on the user's laptop.
        # A cold cache starts the measurement in the background and answers "" for now.
        return _engmod.foreign_cached(key)
    except Exception:                                            # noqa: BLE001
        return ""


def _importable(name: str) -> bool:
    """Is the package installed? `find_spec`, which executes nothing.

    It used to be `__import__(name)`. That imported torch / TTS / onnxruntime into the
    app's own process just to answer a yes/no question — and a native library loaded next
    to Qt's own can end the process with no traceback. "Auto close aaguthu" was that.
    A spec lookup cannot crash anything: it reads the file system and stops there.
    """
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:                                            # noqa: BLE001
        return False


def _piper_ready() -> bool:
    try:
        from .ai.voice import piper_available
        return bool(piper_available())
    except Exception:                                            # noqa: BLE001
        return False


def _piper_parts() -> tuple[str, int]:
    """(the interpreter that has piper, how many voices it can speak). Never blocks.

    Cached answers only: the real search runs in the background (`discover_async`) and
    this is read on the path that decides how to speak a sentence.
    """
    try:
        from .ai import voice as _voice
        from . import piper_engine
        exe = piper_engine.known_python()
        voices = len(_voice.piper_voices())
        return str(exe), int(voices)
    except Exception:                                            # noqa: BLE001
        return "", 0


def route(lang: str) -> str:
    """Which engine should speak `lang`. Pure function — this is the testable bit."""
    code = (lang or "en").split("-")[0].lower()
    have = engines()
    if code == "ta" or code in INDIC_LANGS:
        if have["indicf5"]["available"] and reference():
            return "indicf5"
        return "piper" if have["piper"]["available"] else "sapi"
    if have["xtts"]["available"] and reference() and code in XTTS_LANGS:
        return "xtts"
    if have["piper"]["available"] and code in PIPER_LANGS:
        return "piper"
    return "sapi"


def plan() -> dict:
    """Everything a person needs to know, without guessing."""
    have = engines()
    ref = reference()
    t = transcript()
    return {
        "engines": have,
        "reference": str(ref) if ref else "",
        "reference_seconds": round(_seconds(ref), 2) if ref else 0.0,
        "transcript": bool(t),
        "promised": {code: name for code, (_e, name) in PROMISED.items()},
        "order": ["indicf5 for Tamil and Hindi (the promise)", "xtts for English",
                  "the other 9 Indic + 16 XTTS languages are a bonus, not a claim",
                  "piper (same language, no cloning)", "Windows SAPI"],
        "limits": [
            "XTTS-v2 cannot speak Tamil; IndicF5 can.",
            "IndicF5 wants a GPU. On CPU it is slow enough to be noticeable.",
            "A clone copies the recording: music or hiss in the clip becomes music or hiss.",
            "XTTS-v2 weights are CPML — personal / non-commercial use.",
        ],
    }


# ---------------------------------------------------------------- reference
def _ffmpeg() -> str:
    from . import paths
    return paths.which("ffmpeg")


def _seconds(path: Path) -> float:
    try:
        with wave.open(str(path)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


def _read_mono(path: Path) -> tuple[list[float], int]:
    import array
    with wave.open(str(path)) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("expected 16-bit mono PCM")
        sr = w.getframerate()
        data = array.array("h")
        data.frombytes(w.readframes(w.getnframes()))
    scale = 1.0 / 32768.0
    return [s * scale for s in data], sr


def _read_pcm_any(path: Path) -> tuple[list[float], int]:
    """Read ANY uncompressed WAV into mono floats — no ffmpeg involved.

    The old code sent everything that was not already 16-bit mono through ffmpeg. On a
    machine without ffmpeg that meant "this file cannot be imported", for a file Python
    can read by itself. Now only real codecs (mp3, mp4, m4a, webm …) need ffmpeg.
    """
    import array

    with wave.open(str(path)) as w:
        channels = w.getnchannels()
        width = w.getsampwidth()
        sr = w.getframerate()
        frames = w.readframes(w.getnframes())
    if width == 1:                                  # 8-bit unsigned
        raw = array.array("B", frames)
        values = [(v - 128) / 128.0 for v in raw]
    elif width == 2:
        raw = array.array("h")
        raw.frombytes(frames)
        if sys.byteorder == "big":
            raw.byteswap()
        values = [v / 32768.0 for v in raw]
    elif width == 4:
        raw = array.array("i")
        raw.frombytes(frames)
        if sys.byteorder == "big":
            raw.byteswap()
        values = [v / 2147483648.0 for v in raw]
    else:
        raise ValueError(f"unsupported sample width: {width} bytes")
    if channels > 1:                                # average the channels
        values = [sum(values[i:i + channels]) / channels
                  for i in range(0, len(values) - channels + 1, channels)]
    return values, sr


def _resample(samples: list[float], sr: int, target: int = SAMPLE_RATE) -> list[float]:
    """Linear resample. Good enough for a voice reference; the engines do their own
    conversion anyway — this just keeps the file's promise (24 kHz)."""
    if sr == target or not samples:
        return samples
    ratio = target / float(sr)
    out_len = int(len(samples) * ratio)
    out = [0.0] * out_len
    for i in range(out_len):
        pos = i / ratio
        j = int(pos)
        frac = pos - j
        a = samples[j] if j < len(samples) else samples[-1]
        b = samples[j + 1] if j + 1 < len(samples) else a
        out[i] = a + (b - a) * frac
    return out


def _canonical(path: Path) -> bool:
    """Already 16-bit mono? Then a WAV can be read directly instead of via ffmpeg."""
    try:
        with wave.open(str(path)) as w:
            return w.getnchannels() == 1 and w.getsampwidth() == 2
    except Exception:
        return False


def _write_mono(samples: list[float], sr: int, path: Path) -> None:
    import array
    clipped = [max(-1.0, min(1.0, s)) for s in samples]
    data = array.array("h", (int(s * 32767) for s in clipped))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def speech_segments(samples: list[float], sr: int,
                    min_length: float = 0.25) -> list[tuple[int, int]]:
    """Where the talking is: energy VAD, 30 ms frames, 350 ms of silence ends a run.

    Returns [(start_sample, end_sample), ...] in order, each at least `min_length`
    long. Silence between them is real silence, not a pause inside a sentence.
    """
    win = max(1, int(0.03 * sr))
    frames = [samples[i:i + win] for i in range(0, max(0, len(samples) - win), win)]
    if not frames:
        return []
    energy = [sum(s * s for s in f) / len(f) for f in frames]
    peak = max(energy) or 1e-9
    floor = peak * 0.002                     # ~ -27 dB under the loudest frame
    voiced = [e > floor for e in energy]

    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(voiced):
        if not voiced[i]:
            i += 1
            continue
        start = i
        gap = 0
        while i < len(voiced):
            if voiced[i]:
                gap = 0
            else:
                gap += 1
                if gap * 0.03 > 0.35:
                    break
            i += 1
        end = i - gap
        if (end - start) * 0.03 >= min_length:
            runs.append((start * win, end * win))
    return runs


def best_window(samples: list[float], sr: int,
                target: float = IDEAL_SECONDS) -> tuple[int, int]:
    """The longest continuous stretch of speech, capped at `target` seconds."""
    segs = speech_segments(samples, sr)
    if not segs:
        return 0, min(len(samples), int(target * sr))
    start, end = max(segs, key=lambda ab: ab[1] - ab[0])
    limit = int(target * sr)
    if end - start > limit:
        # keep the middle of the run: the edges are usually a half-spoken word
        pad = (end - start - limit) // 2
        start += pad
        end = start + limit
    return max(0, start), min(len(samples), end)


def stitch(samples: list[float], sr: int, segs: list[tuple[int, int]],
           target: float = 12.0, gap: float = 0.12) -> tuple[list[float], int]:
    """Join pieces of speech, in order, until `target` seconds — for an edited clip.

    An 12-second reel with cuts and music gaps has no single usable 10-second run;
    refusing it would be useless. Splicing with short fades is honest and works, as
    long as the caller says so — a clone from spliced audio keeps the edits' tone.
    """
    out: list[float] = []
    used = 0
    need = int(target * sr)
    pad = [0.0] * int(gap * sr)
    fade = max(1, int(0.008 * sr))
    for start, end in segs:
        if len(out) >= need:
            break
        piece = list(samples[start:min(end, start + (need - len(out)))])
        for i in range(min(fade, len(piece))):
            k = i / fade
            piece[i] *= k
            piece[-1 - i] *= k
        out.extend(piece)
        out.extend(pad)
        used += 1
    return out[:need], used


def _normalise(samples: list[float], target_rms: float = 0.10,
               peak_ceiling: float = 0.79) -> list[float]:
    if not samples:
        return samples
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 or 1e-9
    gain = target_rms / rms
    peak = max(abs(s) for s in samples) or 1e-9
    gain = min(gain, peak_ceiling / peak)
    return [s * gain for s in samples]


def analyse(path: str | Path) -> dict:
    """How good is this clip as a clone reference? Numbers, not opinions.

    `background_db` is the quietest tenth of the frames, `speech_db` the loudest
    tenth; `snr_db` is the difference. A music bed raises the background, so a low
    SNR means the clone will carry that bed with it.
    """
    import numpy as np
    p = Path(str(path)).expanduser()
    read_from = p
    if p.suffix.lower() not in (".wav", ".wave"):
        # analyse() reads PCM, not codecs, so convert once — with the app's own
        # decoders (arcdesk/audio.py), never with a program the person has to install.
        tmp = Path(str(p) + ".analyse.wav")
        try:
            samples, sr = audio.decode(p)
            _write_mono(samples, sr, tmp)
        except audio.AudioDecodeError as exc:
            return {"path": str(p), "seconds": 0.0, "speech_db": -120.0,
                    "background_db": -120.0, "snr_db": 0.0, "clip_pct": 0.0,
                    "grade": "unknown", "advice": f"could not read it: {exc}"}
        read_from = tmp
    out = {"path": str(p), "seconds": 0.0, "speech_db": -120.0, "background_db": -120.0,
           "snr_db": 0.0, "clip_pct": 0.0, "grade": "poor", "advice": ""}
    try:
        with wave.open(str(read_from)) as w:
            sr = w.getframerate()
            raw = w.readframes(w.getnframes())
        if not raw:
            out["advice"] = "the file has no audio in it"
            out["grade"] = "unknown"
            return out
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    except Exception as exc:                                    # noqa: BLE001
        out["advice"] = f"could not read it: {type(exc).__name__}: {exc}"
        return out
    finally:
        if read_from != p:
            try:
                read_from.unlink()
            except OSError:
                pass
    if not len(x):
        out["advice"] = "the file is empty"
        return out
    out["seconds"] = round(len(x) / sr, 2)
    out["clip_pct"] = round(float(np.mean(np.abs(x) > 0.98)) * 100, 3)
    win = max(1, int(0.03 * sr))
    frames = [x[i:i + win] for i in range(0, max(1, len(x) - win), win)]
    rms = np.array([float(np.sqrt(np.mean(f * f))) + 1e-9 for f in frames])
    db = 20 * np.log10(rms)
    out["background_db"] = round(float(np.percentile(db, 10)), 1)
    out["speech_db"] = round(float(np.percentile(db, 90)), 1)
    out["snr_db"] = round(out["speech_db"] - out["background_db"], 1)
    # Reported, not used to excuse a bad score: a heavily noisy clip also has no
    # quiet frames, and calling that "good" because there was nowhere quiet to look
    # would be exactly the kind of flattery this project refuses.
    out["quiet_ratio"] = round(float(np.mean(db < (out["speech_db"] - 15))), 3)

    secs, snr, clip = out["seconds"], out["snr_db"], out["clip_pct"]
    advice = []
    if secs < 6:
        advice.append(f"only {secs:g} s — add ~{max(0, 10 - secs):.0f} s more for a clone "
                      f"that keeps your rhythm, not just your tone")
    elif secs < 8:
        advice.append(f"{secs:g} s is workable; 10-12 s is noticeably better")
    if snr < 18:
        advice.append(f"background is only {snr:g} dB below your voice — run "
                      f"tools/clean_voice.py, or record in a quieter room")
    if clip > 0.5:
        advice.append(f"{clip:g}% of samples are at full scale (clipped) — turn the "
                      f"mic gain down and record again")
    if out["quiet_ratio"] < 0.03 and snr >= 25:
        advice.append("there is no pause in this clip, so the noise floor reading is a "
                      "best guess — a clip with natural pauses grades more reliably")
    clean = snr >= 25 and clip <= 0.5
    if clean and 8 <= secs <= 20:
        out["grade"] = "good"
    elif clean and secs < 8:
        out["grade"] = "short"          # clean voice, just not enough of it
    elif snr >= 15 and secs >= 4 and clip <= 2:
        out["grade"] = "workable"
    else:
        out["grade"] = "poor"
    out["advice"] = "; ".join(advice) or "good reference"
    return out


def quality(path: str | Path | None = None) -> dict:
    """Grade the current reference (or the file given)."""
    target = path or reference()
    if not target:
        return {"grade": "none", "advice": "no reference imported yet"}
    return analyse(target)


def load_audio(path: str | Path) -> tuple[list[float], int]:
    """Read ANY audio file into mono floats — and fetch a small decoder if one is missing.

    This is the single door the rest of the app uses. No ffmpeg, no shopping list handed
    to the person: if the file needs a reader this PC does not have, `audio` installs the
    smallest one that will do it and the file is read straight after.
    """
    p = Path(str(path)).expanduser()
    try:
        return audio.decode(p)
    except audio.AudioDecodeError as first:
        ok, detail = audio.install_decoder(p.suffix)
        if not ok:
            raise audio.AudioDecodeError(
                f"I could not read {p.name} and I could not install a decoder for it "
                f"either ({detail}). Without internet, exporting the clip as a .wav "
                f"will always work.") from None
        try:
            return audio.decode(p)
        except audio.AudioDecodeError as second:
            raise audio.AudioDecodeError(f"{second} ({detail})") from None


def import_reference(src: str, transcript_text: str = "") -> dict:
    """Turn any audio/video file into the 24 kHz mono clip the clone engines want.

    Returns {"ok", "path", "seconds", "source", "message"}. Never raises.
    """
    source = Path(str(src)).expanduser()
    if not source.exists():
        return {"ok": False, "message": f"no such file: {source}"}

    work = voice_dir()
    try:
        samples, sr = load_audio(source)

        if sr != SAMPLE_RATE:                 # the engines want 24 kHz; keep the promise
            samples = _resample(samples, sr, SAMPLE_RATE)
            sr = SAMPLE_RATE
        segs = speech_segments(samples, sr)
        longest = max((b - a for a, b in segs), default=0) / sr
        note = ""
        if longest >= MIN_SECONDS:
            start, end = best_window(samples, sr)
            picked = _normalise(samples[start:end])
        else:
            picked, used = stitch(samples, sr, segs, target=IDEAL_SECONDS)
            picked = _normalise(picked)
            if used > 1:
                note = (f" — stitched from {used} separate pieces of speech, because this "
                        f"clip has cuts in it. One continuous 10-12 s recording will clone "
                        f"noticeably better.")
        if len(picked) / sr < MIN_SECONDS:
            return {"ok": False,
                    "message": f"only {len(picked) / sr:.1f} s of speech found — I need at "
                               f"least {MIN_SECONDS:g} s, ideally {IDEAL_SECONDS:g} s of "
                               f"one person talking with no music"}
        out = work / "reference.wav"
        _write_mono(picked, sr, out)
        if transcript_text.strip():
            _set_transcript(transcript_text)
        speak_text = transcript()
        graded = analyse(out)
        return {"ok": True, "path": str(out), "seconds": round(len(picked) / sr, 2),
                "grade": graded["grade"], "snr_db": graded["snr_db"],
                "background_db": graded["background_db"],
                "advice": graded["advice"],
                "source": str(source),
                "transcript": speak_text,
                "message": (f"reference ready: {len(picked) / sr:.1f} s, {sr // 1000} kHz "
                            f"mono{note}"
                            + ("" if speak_text else " — add the words it says with "
                               "`--transcript`, IndicF5 needs them")
                            + f" [{graded['grade']}: {graded['advice']}]")}
    except Exception as exc:                                    # noqa: BLE001
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}


# -------------------------------------------------------------------- speak
def speak(text: str, lang: str = "en", wav: str = "") -> bool:
    """Speak in the cloned voice. False = nothing happened, fall back."""
    if not (text or "").strip():
        return False
    ref = reference()
    engine = route(lang)
    try:
        if ref and engine in ("indicf5", "xtts"):
            return _speak_in_a_child(text, lang, ref, wav, engine)
        return False            # piper / sapi are handled by voice.py itself
    except Exception:                                            # noqa: BLE001
        return False


def _speak_in_a_child(text: str, lang: str, ref: Path, wav: str, engine: str) -> bool:
    """Produce the sentence in ANOTHER process, whichever interpreter has the engine.

    Why this is not negotiable (the report: *"yethavathu select pana application crash aagi,
    close aaguthu"*): `transformers` + `torch` + `AutoModel.from_pretrained(…,
    trust_remote_code=True)` used to run in the window's own process. That is
    ~1 GB of CUDA-linked DLLs next to Qt's own, plus a *repo's* code executing inside the
    GUI process, plus a model load that freezes the drawing thread for tens of seconds.
    On Windows a clashing DLL does not raise — it ends the process with no traceback, which
    is exactly "the app closed by itself". The app has always known this for the installed
    .exe (that is what the private engine folder is for); it was still true for a plain
    checkout that happened to have the packages installed.

    So: the private folder first (what the Install button fills), then any interpreter the
    person already installed the engine into, then — last — this same interpreter, but as
    a CHILD process, where a crash costs one sentence instead of the window.
    """
    from . import engines as _engmod
    other = (_CACHE.get("data") or {}).get(engine, {}).get("foreign") or ""
    python = ""
    if _engmod.sidecar_ready(engine):
        python = ""                                   # the app's own private folder
    elif other:
        python = other
    elif _local_engine(engine):
        python = sys.executable                       # same python, separate process
    else:
        return False                                  # nothing on this PC can speak it
    return _sidecar_speak(text, lang, ref, wav, engine, _engmod, python=python)


def _local_engine(key: str) -> bool:
    """Can THIS process import the engine's packages? False in the frozen app."""
    module = {"indicf5": "transformers", "xtts": "TTS"}.get(key, "")
    return bool(module) and _importable(module)


def _sidecar_speak(text: str, lang: str, ref: Path, wav: str, engine: str, engmod,
                   python: str = "") -> bool:
    """One sentence through another interpreter (the private folder, or one you already
    installed the engine into), then play the wav."""
    out = wav or str(voice_dir() / f"last_{engine}.wav")
    got = engmod.sidecar_speak(text, lang, str(ref), transcript() or "", out, engine,
                               python=python)
    if not got.get("ok"):
        return False
    return True if wav else _play_file(Path(got["wav"] or out))


def _indicf5(text: str, lang: str, ref: Path, wav: str) -> bool:
    """Kept for reference only — NEVER called. See `_speak_in_a_child`.

    Running this inside the window's process is what ends the app on Windows with no
    traceback. It is left here so the next person can read what the child does, and it
    refuses to run unless `ARCDESK_ALLOW_INPROCESS_TTS=1` is set by hand (nothing sets it).
    """
    if os.environ.get("ARCDESK_ALLOW_INPROCESS_TTS") != "1":
        return False
    try:
        import numpy as np
        from transformers import AutoModel
    except Exception:
        return False
    model_path = engines()["indicf5"]["model"]
    if not model_path:
        return False
    try:
        model = AutoModel.from_pretrained(model_path, trust_remote_code=True)
        audio = model(text, ref_audio_path=str(ref), ref_text=transcript() or None)
        if isinstance(audio, tuple):
            audio = audio[0]
        if wav:
            _save_int16(np.asarray(audio), wav)
            return True
        return _play_array(np.asarray(audio))
    except Exception:
        return False


def _xtts(text: str, lang: str, ref: Path, wav: str) -> bool:
    """Kept for reference only — NEVER called. See `_speak_in_a_child`."""
    if os.environ.get("ARCDESK_ALLOW_INPROCESS_TTS") != "1":
        return False
    try:
        from TTS.api import TTS
    except Exception:
        return False
    model_path = engines()["xtts"]["model"]
    if not model_path:
        return False
    try:
        tts = TTS(model_path=model_path).to("cpu")
        tts.tts_to_file(text=text, speaker_wav=str(ref),
                        language=(lang or "en").split("-")[0],
                        file_path=wav or str(voice_dir() / "last_tts.wav"))
        return bool(wav) or _play_file(voice_dir() / "last_tts.wav")
    except Exception:
        return False


def _save_int16(arr, path: str) -> None:
    import numpy as np
    a = np.asarray(arr, dtype=np.float32)
    a = np.clip(a / (np.max(np.abs(a)) + 1e-9) * 0.9, -1, 1)
    import wave as _w
    with _w.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((a * 32767).astype("<i2").tobytes())


def _play_array(arr) -> bool:
    tmp = voice_dir() / "last_tts.wav"
    _save_int16(arr, str(tmp))
    return _play_file(tmp)


def _play_file(path: Path) -> bool:
    """Play a WAV with no extra dependency where we can help it."""
    try:
        import sys
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return True
        if shutil.which("aplay"):
            quiet.run(["aplay", "-q", str(path)], timeout=120)
            return True
        if shutil.which("afplay"):
            quiet.run(["afplay", str(path)], timeout=120)
            return True
    except Exception:
        return False
    return False


def describe() -> str:
    """One line for the doctor / settings screen."""
    p = plan()
    ready = [k for k, v in p["engines"].items() if v["available"]]
    ref = f"{p['reference_seconds']:g} s reference" if p["reference"] else "no reference clip"
    return (f"voice clone: {', '.join(ready) or 'none installed'} · {ref} · "
            f"Tamil → {route('ta')}, English → {route('en')}")
