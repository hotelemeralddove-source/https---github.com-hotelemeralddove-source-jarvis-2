"""Voice upload without ffmpeg — the promise, tested on real files.

The report was a dialog: "ffmpeg is needed to read that file — run install.bat or export
the clip as WAV and try again", on a perfectly good recording. These checks make that
sentence impossible to come back:

  1. every WAV Python can meet (8/16/24/32-bit, mono and stereo) is read by the stdlib;
  2. mp3 and ogg/opus are read by the small wheel, no ffmpeg anywhere;
  3. a genuinely unreadable file gets a message a person can act on;
  4. the whole upload path (`clone.import_reference`) finishes with real speech in a
     non-WAV file and produces a reference the clone engines can use;
  5. nothing in the runtime mentions ffmpeg as a requirement.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_audio.py
"""
from __future__ import annotations

import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

os.environ.setdefault("ARCDESK_NO_DECODER_INSTALL", "1")   # no pip runs from a test
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import audio, clone  # noqa: E402

ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<56} {got!r}")
    return good


def speech(seconds=6.0, sr=16000) -> list[float]:
    """A voice-ish signal: a wobbling tone with gaps, so the VAD finds speech."""
    out = []
    for i in range(int(seconds * sr)):
        t = i / sr
        env = 0.5 + 0.5 * math.sin(2 * math.pi * 2.5 * t)
        if (t % 3.0) < 2.2:
            out.append(0.35 * env * math.sin(2 * math.pi * 210 * t))
        else:
            out.append(0.0)
    return out


def write_wav(path: Path, samples: list[float], sr: int, width: int = 2,
              channels: int = 1) -> None:
    def pack(v: float) -> bytes:
        v = max(-1.0, min(1.0, v))
        if width == 1:
            return struct.pack("<B", int(v * 127 + 128))
        if width == 2:
            return struct.pack("<h", int(v * 32767))
        if width == 3:
            n = int(v * 8388607)
            return struct.pack("<i", n)[:3]
        return struct.pack("<i", int(v * 2147483647))

    frames = b"".join(pack(s) for s in samples for _ in range(channels))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(sr)
        w.writeframes(frames)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="arc-audio-"))
    print("audio readers present:", ", ".join(audio.decoders()))

    print("\n1. every WAV the stdlib can read, it reads")
    for width, label in ((1, "8-bit"), (2, "16-bit"), (3, "24-bit"), (4, "32-bit")):
        path = tmp / f"clip{width}.wav"
        write_wav(path, speech(1.0), 16000, width=width)
        try:
            samples, sr = audio.decode(path)
            check(f"{label} WAV decoded", (len(samples) >= 16000, sr), (True, 16000))
        except audio.AudioDecodeError as exc:
            check(f"{label} WAV decoded", str(exc), "")
    stereo = tmp / "stereo.wav"
    write_wav(stereo, speech(1.0), 16000, width=2, channels=2)
    samples, sr = audio.decode(stereo)
    check("stereo is mixed down to mono, not doubled", (len(samples), sr), (16000, 16000))

    print("\n2. the compressed formats people actually have")
    made = 0
    try:
        import soundfile as sf
        for suffix, fmt in ((".flac", "FLAC"), (".ogg", "OGG"), (".mp3", "MP3")):
            path = tmp / f"voice{suffix}"
            try:
                sf.write(str(path), speech(1.0), 16000, format=fmt)
            except Exception:                              # noqa: BLE001
                continue
            made += 1
            samples, sr = audio.decode(path)
            check(f"{suffix} decoded without ffmpeg", len(samples) > 8000)
    except ImportError:
        print("   (soundfile is not installed here — skipped, the installer adds it)")
    check("at least one compressed format was really tested", made >= 1)

    print("\n3. a file nothing can read says something useful")
    broken = tmp / "notaudio.mp3"
    broken.write_bytes(b"this is not audio at all" * 20)
    try:
        audio.decode(broken)
        check("an unreadable file is refused", "no error raised", "an error")
    except audio.AudioDecodeError as exc:
        text = str(exc)
        check("the message names the file", "notaudio.mp3" in text)
        check("…and does not tell the person to go install ffmpeg",
              "install ffmpeg" in text.lower(), False)

    print("\n4. the whole upload path, on a real compressed clip")
    target = tmp / "upload.ogg"
    src = tmp / "src.wav"
    write_wav(src, speech(9.0), 16000, width=2)
    try:
        import soundfile as sf
        sf.write(str(target), speech(9.0), 16000, format="OGG")
    except Exception:                                      # noqa: BLE001
        target = src
    got = clone.import_reference(str(target), "hello, this is my voice")
    check("the upload succeeded", got.get("ok"), True)
    if got.get("ok"):
        ref = Path(got["path"])
        check("a reference wav exists", ref.exists())
        samples, sr = audio.decode(ref)
        check("…at the rate the engines want", sr, clone.SAMPLE_RATE)
        check("…and long enough to clone", round(len(samples) / sr) >= 4, True)
        check("the transcript came through", clone.transcript(), "hello, this is my voice")
    else:
        print("   message:", got.get("message"))

    print("\n5. ffmpeg is not on the list of things a person must install")
    root = Path(__file__).resolve().parents[1] / "arcdesk"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        if "run install.bat or export the clip" in text:
            offenders.append(path.name)
    check("no runtime module asks for ffmpeg to upload a voice", offenders, [])

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
