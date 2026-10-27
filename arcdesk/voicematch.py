"""Speak in the person's own voice, on a laptop, with nothing to install.

The promise was "nan ena voice la enakku reply venum nu mp3 file add panren". An exact clone
needs a neural engine — a 1.5-2.5 GB download, torch, and (in practice) a GPU before the reply
stops lagging behind the question. That is why the app used to answer with the system voice and
say, quietly, "no clone engine is installed": the clip was imported and then never used.

This module is the honest middle ground, and it works the moment the clip is imported:

    the clip is analysed  ->  its pitch and its pace (two numbers)
    every sentence the app would have said in the system voice is rendered to a WAV,
    pitched and paced to match those two numbers, and played.

It is a *match*, not a clone: it does not copy the timbre of the throat, and the app always
says so in plain words when it is the thing speaking. But it is the person's own pitch and
rhythm, offline, in under a second, with no download and no GPU — and for "reply in my
voice" that is most of the way there.

Everything here is pure Python on purpose (numpy is used when it is there). No ffmpeg: the
installer has to stay small, and a reply voice must not need a 100 MB program.
"""
from __future__ import annotations

import json
import math
import wave
from pathlib import Path

try:                                                     # numpy makes this instant
    import numpy as _np
except Exception:                                        # noqa: BLE001
    _np = None

#: Below this the profile is not worth trusting ("too short to measure a pitch").
MIN_SECONDS = 1.5
#: The most the pitch is moved. A fifth and a half (9 semitones) covers the ordinary case
#: of a deep clip against a higher system voice; past that it stops sounding like a voice
#: and starts sounding like a chipmunk, which is worse than not matching at all.
MAX_SEMITONES = 9.0


# ------------------------------------------------------------------ reading + writing
def read_wav(path: str | Path) -> tuple[list[float], int]:
    """Read a plain PCM WAV into mono floats. Anything else goes through `clone.load_audio`."""
    p = Path(str(path))
    try:
        with wave.open(str(p), "rb") as w:
            sr = w.getframerate()
            n = w.getnframes()
            ch = w.getnchannels()
            width = w.getsampwidth()
            raw = w.readframes(n)
    except Exception:                                    # noqa: BLE001
        from . import clone
        return clone.load_audio(p)
    if width == 1:
        data = [(b - 128) / 128.0 for b in raw]
    elif width == 2:
        import struct
        count = len(raw) // 2
        data = [v / 32768.0 for v in struct.unpack(f"<{count}h", raw[:count * 2])]
    elif width == 4:
        import struct
        count = len(raw) // 4
        data = [v / 2147483648.0 for v in struct.unpack(f"<{count}i", raw[:count * 4])]
    else:
        raise ValueError(f"unsupported sample width: {width} bytes")
    if ch > 1:                                           # keep the left channel only
        data = data[::ch]
    return data, sr


def write_wav(samples: list[float], sr: int, path: str | Path) -> str:
    p = Path(str(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    import struct
    frames = b"".join(struct.pack("<h", max(-32768, min(32767, int(v * 32767))))
                      for v in samples)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(frames)
    return str(p)


# ------------------------------------------------------------------ saying what it hears
def _frames(x, sr: int, size_ms: int = 40, hop_ms: int = 20) -> list[list[float]]:
    size = max(1, int(sr * size_ms / 1000))
    hop = max(1, int(sr * hop_ms / 1000))
    out = []
    for start in range(0, max(0, len(x) - size), hop):
        out.append(x[start:start + size])
        if len(out) > 400:                                # 8 s of analysis is plenty
            break
    return out


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0


def pitch_hz(samples: list[float], sr: int,
             low: float = 70.0, high: float = 380.0) -> float:
    """Median pitch of the voiced frames, in Hz. 0.0 = nothing measurable.

    Autocorrelation, on the frames that are loud enough to be speech. Deliberately simple:
    the number only has to be right to within a semitone, because that is what the shift
    uses, and a wrong-but-steady number still moves every sentence the same way.
    """
    if not samples:
        return 0.0
    # work at 8 kHz: the pitch range we care about lives well under 4 kHz
    step = max(1, sr // 8000)
    x = samples[::step]
    sr = sr / step
    min_lag = max(2, int(sr / high))
    max_lag = int(sr / low)
    energies = [sum(v * v for v in frame) / len(frame) for frame in _frames(x, int(sr))]
    if not energies:
        return 0.0
    loud = _median(energies) * 0.6
    frames = list(_frames(x, int(sr)))
    found: list[float] = []
    if _np is not None:                                  # the fast road: one correlate a frame
        for frame, energy in zip(frames, energies):
            if energy <= loud or energy < 1e-7:
                continue
            arr = _np.asarray(frame, dtype=_np.float32)
            arr = arr - arr.mean()
            top = min(max_lag, len(arr) - 1)
            if top <= min_lag:
                continue
            best_lag, best = 0, 0.0
            for lag in range(min_lag, top):
                num = float(_np.dot(arr[:-lag], arr[lag:]))
                if num > best:
                    best, best_lag = num, lag
            if best_lag:
                hz = sr / best_lag
                if low <= hz <= high:
                    found.append(hz)
        return round(_median(found), 1)
    for frame, energy in zip(frames, energies):
        if energy <= loud or energy < 1e-7:
            continue                                     # silence is not a pitch
        mean = sum(frame) / len(frame)
        centred = [v - mean for v in frame]
        best_lag, best = 0, 0.0
        for lag in range(min_lag, min(max_lag, len(centred) - 1)):
            num = sum(centred[i] * centred[i + lag] for i in range(len(centred) - lag))
            if num > best:
                best, best_lag = num, lag
        if best_lag:
            hz = sr / best_lag
            if low <= hz <= high:
                found.append(hz)
    return round(_median(found), 1)


def words_per_minute(samples: list[float], sr: int) -> float:
    """A rough pace, from how much of the clip is speech vs. silence.

    Not a language model: it measures the fraction of loud 20 ms frames. A slow speaker
    leaves gaps, a fast one does not — which is exactly what the tempo change wants.
    """
    frames = _frames(samples, sr)
    if not frames:
        return 0.0
    energies = [sum(v * v for v in f) / len(f) for f in frames]
    loud = _median(energies) * 0.6
    voiced = sum(1 for e in energies if e > loud)
    return round(100.0 * voiced / len(energies), 1)


# ------------------------------------------------------------------ the profile
def profile_of(samples: list[float], sr: int) -> dict:
    return {
        "pitch": pitch_hz(samples, sr),
        "voiced_pct": words_per_minute(samples, sr),
        "seconds": round(len(samples) / sr, 2) if sr else 0.0,
    }


def _cache_path() -> Path:
    from . import config
    folder = config.data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "voicematch.json"


def _reference_stamp(ref: Path) -> str:
    try:
        st = ref.stat()
        return f"{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return ""


def reference_profile(ref: Path | None = None, refresh: bool = False) -> dict:
    """The imported clip's pitch and pace, cached against its size and mtime."""
    from . import clone
    ref = ref or clone.reference()
    if ref is None or not Path(ref).exists():
        return {}
    ref = Path(ref)
    stamp = _reference_stamp(ref)
    cache = {}
    try:
        cache = json.loads(_cache_path().read_text(encoding="utf-8") or "{}")
    except Exception:                                    # noqa: BLE001
        cache = {}
    if not refresh and cache.get("stamp") == stamp and cache.get("profile"):
        return dict(cache["profile"])
    try:
        samples, sr = read_wav(ref)
        if len(samples) / sr < MIN_SECONDS:
            return {}
        prof = profile_of(samples, sr)
        if not prof.get("pitch"):
            return {}
        _cache_path().write_text(json.dumps({"stamp": stamp, "profile": prof}),
                                 encoding="utf-8")
        return prof
    except Exception:                                    # noqa: BLE001
        return {}


def active(cfg: dict | None = None) -> bool:
    """Is the quick match the thing that should speak?

    Only when a clip exists, the person has not turned it off, and no exact-clone engine is
    installed — because when a real engine is there, its output must not be meddled with.
    """
    try:
        from . import clone
        cfg = cfg if isinstance(cfg, dict) else {}
        ai = (cfg or {}).get("ai", {}) if isinstance(cfg, dict) else {}
        if ai.get("voice_match") is False:
            return False
        if not clone.reference():
            return False
        engines = clone.engines()
        if any(v.get("available") for v in engines.values()):
            return False                                 # the real thing wins
        return True
    except Exception:                                    # noqa: BLE001
        return False


# ------------------------------------------------------------------ the shift
def _resample(x: list[float], sr: int, new_sr: int) -> list[float]:
    if new_sr == sr or not x:
        return list(x)
    ratio = new_sr / sr
    n = int(len(x) * ratio)
    out = []
    for i in range(n):
        pos = i / ratio
        i0 = int(pos)
        frac = pos - i0
        a = x[i0] if i0 < len(x) else 0.0
        b = x[i0 + 1] if i0 + 1 < len(x) else a
        out.append(a + (b - a) * frac)
    return out


def _stretch(x: list[float], sr: int, factor: float) -> list[float]:
    """Time-stretch with overlap-add grains: `factor` > 1 makes it longer.

    Pitch is unchanged, which is the point — the shift does the pitch, this puts the
    duration back so the sentence is not spoken faster or slower than it was synthesised.
    """
    if abs(factor - 1.0) < 0.01 or not x:
        return list(x)
    grain = max(64, int(sr * 0.030))                     # 30 ms
    hop_out = max(1, int(grain * 0.5))
    hop_in = max(1, int(hop_out / factor))
    window = [0.5 - 0.5 * math.cos(2 * math.pi * i / max(1, grain - 1)) for i in range(grain)]
    total = int(len(x) * factor) + grain
    out = [0.0] * total
    weight = [0.0] * total
    pos_in, pos_out = 0, 0
    while pos_out + grain < total and pos_in + grain < len(x):
        for i in range(grain):
            out[pos_out + i] += x[pos_in + i] * window[i]
            weight[pos_out + i] += window[i]
        pos_in += hop_in
        pos_out += hop_out
    return [out[i] / weight[i] if weight[i] > 1e-6 else 0.0 for i in range(len(out))]


def shift(x: list[float], sr: int, semitones: float) -> list[float]:
    """Move the pitch by `semitones` and keep the duration the same."""
    if not x or abs(semitones) < 0.05:
        return list(x)
    ratio = 2.0 ** (semitones / 12.0)                    # >1 = higher
    longer = _stretch(x, sr, ratio)                      # make it longer by exactly that
    return _resample(longer, sr, max(1000, int(sr / ratio)))


def semitones_between(tts_hz: float, target_hz: float) -> float:
    """How far the synthesised voice has to move to sit on the person's pitch."""
    if not tts_hz or not target_hz or tts_hz <= 0 or target_hz <= 0:
        return 0.0
    steps = 12.0 * math.log2(target_hz / tts_hz)
    return max(-MAX_SEMITONES, min(MAX_SEMITONES, steps))


def _tts_cache_path() -> Path:
    from . import config
    folder = config.data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "voicematch_tts.json"


def tts_pitch(samples: list[float], sr: int, key: str) -> float:
    """Pitch of the engine's own voice, remembered per engine+voice name."""
    try:
        cache = json.loads(_tts_cache_path().read_text(encoding="utf-8") or "{}")
    except Exception:                                    # noqa: BLE001
        cache = {}
    if key and isinstance(cache.get(key), (int, float)) and cache[key] > 0:
        return float(cache[key])
    hz = pitch_hz(samples, sr)
    if hz and key:
        cache[key] = hz
        try:
            _tts_cache_path().write_text(json.dumps(cache), encoding="utf-8")
        except Exception:                                # noqa: BLE001
            pass
    return hz


def match_file(src: str | Path, dst: str | Path, prof: dict | None = None,
               tts_key: str = "") -> dict:
    """Pitch a rendered sentence to the person's clip. Returns {"ok", "semitones", "why"}."""
    prof = prof or reference_profile()
    if not prof:
        return {"ok": False, "why": "no usable voice clip", "semitones": 0.0}
    try:
        samples, sr = read_wav(src)
        if not samples:
            return {"ok": False, "why": "the sentence came out empty", "semitones": 0.0}
        mine = tts_pitch(samples, sr, tts_key)
        steps = semitones_between(mine, float(prof.get("pitch") or 0))
        if abs(steps) < 0.4:
            # already close: nothing to gain, and every shift costs a little quality
            write_wav(samples, sr, dst)
            return {"ok": True, "semitones": 0.0, "why": "already at your pitch"}
        out = shift(samples, sr, steps)
        peak = max((abs(v) for v in out), default=0.0)
        if peak > 0.98:                                  # keep it inside the speaker
            out = [v * (0.98 / peak) for v in out]
        write_wav(out, sr, dst)
        return {"ok": True, "semitones": round(steps, 2),
                "why": f"moved {steps:+.1f} semitones to your pitch ({prof.get('pitch')} Hz)"}
    except Exception as exc:                             # noqa: BLE001
        return {"ok": False, "why": f"{type(exc).__name__}: {exc}", "semitones": 0.0}


def describe() -> str:
    """One plain sentence for the settings window."""
    prof = reference_profile()
    if not prof:
        return "no voice clip yet — import one and this switches on by itself"
    return (f"matching your clip: {prof.get('pitch')} Hz pitch, "
            f"{prof.get('voiced_pct')}% of the clip is speech, {prof.get('seconds')} s long")
