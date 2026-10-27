"""Read any audio file into plain floats — without asking the person to install ffmpeg.

The report, from the voice tab:

    "That voice was not added — ffmpeg is needed to read that file — run install.bat
     or export the clip as WAV and try again"

That is a dead end dressed as advice. The clip was fine; the app just had no decoder.
ffmpeg is a 100 MB program this app deliberately does not carry (the installer has to
stay small), so "install ffmpeg" is not something a person should be told to do either.

So the app brings its own decoders, smallest first, and none of them is ffmpeg:

    1. `wave`        — the standard library. Reads every WAV, any bit depth.
    2. `soundfile`   — a ~2 MB wheel with libsndfile inside it: WAV, FLAC, OGG, **OPUS**
                       (WhatsApp voice notes), and MP3 in libsndfile 1.1+.
    3. `miniaudio`   — a ~1 MB wheel: MP3, WAV, FLAC, Vorbis.
    4. `av` (PyAV)   — ~30 MB, but it is FFmpeg as a *library*: M4A/AAC, MP4, WEBM, MKV,
                       anything. Used only when nothing smaller can do the job.
    5. `ffmpeg.exe`  — if the machine happens to have one, because why not.

If none of them is installed, `decode()` **installs one itself** (`install_decoder()`) and
tries again. That is the "auto download" rule: the program fetches what it needs, quietly,
instead of printing a shopping list at the person.
"""
from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path

#: Codecs the small wheels handle well; anything else goes straight to PyAV.
_SMALL_OK = {".wav", ".flac", ".ogg", ".oga", ".opus", ".mp3"}
#: Containers that need a real demuxer (PyAV or ffmpeg).
_BIG_SUFFIXES = {".m4a", ".mp4", ".aac", ".webm", ".mkv", ".mov", ".m4b", ".amr", ".wma"}


class AudioDecodeError(RuntimeError):
    """Nothing could read the file. The message is written for the person, not a log."""


def _importable(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:                                            # noqa: BLE001
        return False


def decoders() -> list[str]:
    """Which readers are available right now, best-first."""
    out = ["wave"]
    for name in ("soundfile", "miniaudio", "av"):
        if _importable(name):
            out.append(name)
    return out


# --------------------------------------------------------------------- readers
def _read_wave(path: Path) -> tuple[list[float], int]:
    """Every WAV Python can read by itself: 8/16/24/32-bit integer, mono or stereo."""
    import array

    with wave.open(str(path)) as w:
        channels = w.getnchannels()
        width = w.getsampwidth()
        sr = w.getframerate()
        frames = w.readframes(w.getnframes())

    if width == 1:                                   # 8-bit unsigned
        raw = array.array("B", frames)
        values = [(v - 128) / 128.0 for v in raw]
    elif width == 2:
        raw = array.array("h")
        raw.frombytes(frames)
        if sys.byteorder == "big":
            raw.byteswap()
        values = [v / 32768.0 for v in raw]
    elif width == 3:                                 # 24-bit, very common in the wild
        values = []
        for i in range(0, len(frames) - 2, 3):
            v = frames[i] | (frames[i + 1] << 8) | (frames[i + 2] << 16)
            if v & 0x800000:
                v -= 1 << 24
            values.append(v / 8388608.0)
    elif width == 4:
        raw = array.array("i")
        raw.frombytes(frames)
        if sys.byteorder == "big":
            raw.byteswap()
        values = [v / 2147483648.0 for v in raw]
    else:
        raise AudioDecodeError(f"this WAV uses {width * 8}-bit samples, which I cannot read")
    if channels > 1:
        values = [sum(values[i:i + channels]) / channels
                  for i in range(0, len(values) - channels + 1, channels)]
    return values, sr


def _read_soundfile(path: Path) -> tuple[list[float], int]:
    import soundfile as sf                                       # noqa: PLC0415
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.size == 0:
        raise AudioDecodeError("that file is silent or empty")
    channels = data.shape[1]
    mono = [float(sum(row) / channels) for row in data] if channels > 1 \
        else [float(v) for v in data[:, 0]]
    return mono, int(sr)


def _read_miniaudio(path: Path) -> tuple[list[float], int]:
    import miniaudio                                             # noqa: PLC0415
    decoded = miniaudio.decode_file(str(path))
    sr = int(decoded.sample_rate)
    channels = int(decoded.nchannels) or 1
    raw = decoded.samples
    if channels > 1:
        mono = [sum(raw[i:i + channels]) / channels
                for i in range(0, len(raw) - channels + 1, channels)]
    else:
        mono = list(raw)
    return [v / 32768.0 for v in mono], sr


def _read_av(path: Path) -> tuple[list[float], int]:
    import av                                                    # noqa: PLC0415
    import numpy as np

    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise AudioDecodeError("that file has no sound in it")
        sr = int(stream.rate or 24000)
        chunks = []
        for frame in container.decode(stream):
            arr = frame.to_ndarray()
            if arr.ndim > 1:
                arr = arr.mean(axis=0)
            chunks.append(arr.astype("float32"))
    if not chunks:
        raise AudioDecodeError("nothing could be decoded from that file")
    data = np.concatenate(chunks)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1.5:                        # integer samples handed back by older PyAV
        data = data / 32768.0
    return [float(v) for v in data], sr


def _read_ffmpeg(path: Path) -> tuple[list[float], int]:
    from . import paths, quiet
    exe = paths.which("ffmpeg")
    if not exe:
        raise AudioDecodeError("no ffmpeg")
    tmp = Path(tempfile.mkdtemp(prefix="arcdec-")) / "out.wav"
    done = quiet.run([exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
                      "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(tmp)],
                     capture_output=True, text=True, timeout=600)
    if done.returncode != 0 or not tmp.exists():
        raise AudioDecodeError(((done.stderr or "") or "ffmpeg failed")[-160:])
    out = _read_wave(tmp)
    try:
        tmp.unlink()
        tmp.parent.rmdir()
    except OSError:
        pass
    return out


_READERS = (
    ("wave", (".wav", ".wave"), _read_wave),
    ("soundfile", tuple(_SMALL_OK | _BIG_SUFFIXES), _read_soundfile),
    ("miniaudio", tuple(_SMALL_OK), _read_miniaudio),
    ("av", tuple(_SMALL_OK | _BIG_SUFFIXES), _read_av),
    ("ffmpeg", tuple(_SMALL_OK | _BIG_SUFFIXES), _read_ffmpeg),
)


def decode(path: str | Path) -> tuple[list[float], int]:
    """Return (mono floats in -1..1, sample rate). Raises AudioDecodeError."""
    p = Path(str(path)).expanduser()
    if not p.exists():
        raise AudioDecodeError(f"I cannot find that file: {p.name}")
    suffix = p.suffix.lower()
    problems: list[str] = []
    for name, suffixes, reader in _READERS:
        if suffix not in suffixes:
            continue
        if name != "wave" and not _importable(name) and name != "ffmpeg":
            continue
        try:
            samples, sr = reader(p)
            if samples and sr:
                return samples, int(sr)
            problems.append(f"{name}: empty")
        except Exception as exc:                                 # noqa: BLE001
            problems.append(f"{name}: {type(exc).__name__}")
    raise AudioDecodeError(
        f"I could not read {p.name}"
        + (f" ({', '.join(problems)})" if problems else "")
        + ". The small decoder is not installed on this PC yet.")


# ------------------------------------------------------------- getting a decoder
def _pip(names: list[str], timeout: float = 600) -> tuple[bool, str]:
    from . import quiet
    done = quiet.run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade",
                      *names], capture_output=True, text=True, timeout=timeout)
    text = ((done.stdout or "") + (done.stderr or "")).strip()
    return done.returncode == 0, text[-300:]


def install_decoder(suffix: str = ".wav", timeout: float = 600) -> tuple[bool, str]:
    """Fetch the smallest decoder that can read this kind of file. No ffmpeg, no admin.

    * OPUS/OGG/MP3/FLAC/WAV  -> `soundfile`  (~2 MB, has libsndfile inside)
    * M4A/MP4/WEBM/MKV/AAC   -> `av`         (~30 MB, FFmpeg as a library)

    Returns (ok, what happened) and never raises.
    """
    import os
    if os.environ.get("ARCDESK_NO_DECODER_INSTALL"):
        # Tests (and anyone offline on purpose) must never start a pip run behind their
        # back. The message still explains itself; nothing is downloaded.
        return False, "installing decoders is disabled here (ARCDESK_NO_DECODER_INSTALL)"
    suffix = (suffix or "").lower()
    wanted = ["av"] if suffix in _BIG_SUFFIXES else ["soundfile"]
    for names in (wanted, ["soundfile"], ["av"], ["miniaudio"]):
        ok, detail = _pip(names, timeout)
        if ok:
            import importlib
            for name in names:
                try:
                    importlib.invalidate_caches()
                    importlib.import_module(name)
                except Exception:                                # noqa: BLE001
                    pass
            return True, f"installed {' '.join(names)} so that voice can be read"
    return False, detail or "the decoder could not be installed (no internet?)"


def can_read(suffix: str) -> bool:
    """True when some *installed* reader claims this extension."""
    suffix = (suffix or "").lower()
    for name, suffixes, _reader in _READERS:
        if suffix in suffixes and (name == "wave" or _importable(name)
                                   or name == "ffmpeg"):
            return True
    return False


def describe() -> str:
    have = decoders()
    return ("audio readers here: " + ", ".join(have)
            + " — ffmpeg is not required for voice upload")
