#!/usr/bin/env python3
"""Say one sentence in a cloned voice, into a wav file. Used by the installed app.

    <engine python> tools/clone_speak.py --engine indicf5 --lang ta \
        --text "vanakkam macha" --reference C:\\...\\reference.wav \
        --transcript "the words in the reference" --out C:\\...\\reply.wav

Why this file exists: a frozen ArcDesk.exe cannot import a package that is installed
later, and torch inside the installer would add about 2 GB. So the app keeps a small
private environment (Settings -> Voice -> Get the reply-voice engine...) and calls THIS
script with that interpreter. The app plays the wav. From the person's side: one button.

It prints one line per stage and exits non-zero on every failure — the app shows the
last line to the person instead of inventing a reason.

    exit 0  wav written
    exit 2  bad arguments / missing reference or model
    exit 3  the engine raised (the message is printed)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ENGINES = ("indicf5", "xtts")


def fail(code: int, message: str) -> int:
    print(f"FAILED: {message}")
    return code


def save_int16(samples, path: Path) -> None:
    """Write float samples as a 16-bit mono wav, peaking at 90% — no clipping, no hiss."""
    import wave

    import numpy as np
    a = np.asarray(samples, dtype=np.float32).reshape(-1)
    if a.size == 0:
        raise ValueError("the engine returned no audio")
    peak = float(np.max(np.abs(a))) or 1.0
    pcm = (np.clip(a / peak * 0.9, -1.0, 1.0) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm.tobytes())


def speak_indicf5(text: str, reference: Path, transcript: str, out: Path) -> int:
    from transformers import AutoModel
    print("loading IndicF5 (first run loads the weights, later runs are quicker)")
    model = AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)
    print("speaking")
    audio = model(text, ref_audio_path=str(reference), ref_text=transcript or None)
    if isinstance(audio, tuple):
        audio = audio[0]
    save_int16(audio, out)
    print(f"wrote {out}")
    return 0


def speak_xtts(text: str, reference: Path, lang: str, out: Path) -> int:
    from TTS.api import TTS
    print("loading XTTS-v2")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
    print("speaking")
    tts.tts_to_file(text=text, speaker_wav=str(reference),
                    language=lang if lang in ("en", "hi") else "en",
                    file_path=str(out))
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="speak one line in a cloned voice")
    ap.add_argument("--engine", choices=ENGINES, required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--transcript", default="")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    reference = Path(args.reference)
    out = Path(args.out)
    if not args.text.strip():
        return fail(2, "empty text")
    if not reference.is_file():
        return fail(2, f"the reference clip is missing: {reference}")

    try:
        if args.engine == "indicf5":
            return speak_indicf5(args.text, reference, args.transcript, out)
        return speak_xtts(args.text, reference, args.lang, out)
    except Exception as exc:                      # noqa: BLE001 — reported, not hidden
        return fail(3, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
