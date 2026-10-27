#!/usr/bin/env python3
"""Voice out, on its own: what ARC will actually pronounce, and how.

    python tools/say.py --voices
    python tools/say.py "drew an elephant; saved to ~/Pictures/arc_elephant_17.png"
    python tools/say.py --tamil
    python tools/say.py "the cat is purple" --wav shots/arc_says.wav
    python tools/say.py --cancel

Nothing here needs the GUI or the network. On Windows the engine is SAPI, on macOS
`say`, on Linux `espeak-ng` — the same three branches the app uses, so what you hear
from this tool is what you will hear from ARC.

The interesting output is not the noise: it is the *sanitised line* and the *chunk
plan*. That is where a reply stops sounding like a log file.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk.ai import voice as V  # noqa: E402

W = 74


def bar(c: str = "─") -> None:
    print(c * W)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="*", help="what ARC should say")
    ap.add_argument("--voices", action="store_true", help="list installed system voices")
    ap.add_argument("--tamil", action="store_true", help="speak a Tamil sample")
    ap.add_argument("--wav", metavar="FILE", help="render to a file instead of the speakers")
    ap.add_argument("--cancel", action="store_true",
                    help="prove that a second sentence silences the first")
    ap.add_argument("--dry", action="store_true", help="plan only, make no sound")
    ap.add_argument("--rate", type=int, default=1, help="-5..5, default 1")
    ap.add_argument("--voice-name", default="", help="system voice to select")
    args = ap.parse_args()

    cfg = {"ai": {"voice": True, "voice_rate": args.rate, "voice_name": args.voice_name}}
    v = V.Voice(cfg)

    print("ARC DESK · voice out")
    bar("=")
    print(f"    engine               {v.tts_label()}")
    print(f"    available            {'yes' if v.tts_available else 'NO — install espeak-ng / use Windows'}")

    if args.voices:
        names = v.voices()
        print(f"    installed voices     {len(names)}")
        for n in names[:40]:
            print(f"      · {n}")
        if not names:
            print("      (default voice only)")
        return 0

    if args.cancel:
        return cancel_demo(v)

    text = " ".join(args.text).strip()
    if args.tamil:
        text = ("நான் தயார். எலிஃபண்ட் வரைந்துவிட்டேன். "
                "படம் Pictures folder-ல சேமிச்சிருக்கு.")
    if not text:
        text = ("Drew an elephant in that colour. Saved to "
                "~/Pictures/ArcArt/arc_elephant_1792666838.png — "
                "run ComfyUI on :8188 for photorealistic images.")

    clean = V.sanitise(text)
    parts = V.chunks(clean)
    lang = V.speech_lang(text)

    print()
    print("[1] AS WRITTEN (what the reply bubble shows)")
    for line in _wrap(text, 66):
        print("      " + line)

    print("\n[2] AS SPOKEN (voice.sanitise)")
    for line in _wrap(clean, 66):
        print("      " + line)
    print(f"      {'':<2}{len(text)} chars → {len(clean)} chars · "
          f"language {lang or 'engine default'}")

    print(f"\n[3] CHUNK PLAN — {len(parts)} utterance(s), {V.CHUNK} char target")
    for i, p in enumerate(parts, 1):
        print(f"      {i}. [{len(p):>3}] {p[:60]}{'…' if len(p) > 60 else ''}")
    print("      Why chunk at all: the first words start sooner, a cancel can land")
    print("      between sentences, and one dead engine call cannot hang for a minute.")

    if args.dry:
        print("\n[4] skipped (--dry)")
        return 0

    if args.wav:
        out = Path(args.wav)
        out.parent.mkdir(parents=True, exist_ok=True)
        print(f"\n[4] RENDER → {out}")
        t0 = time.time()
        v._speak_to_file(text, str(out))
        ok = out.exists() and out.stat().st_size > 1000
        print(f"      {'wrote' if ok else 'FAILED'} {out.stat().st_size if out.exists() else 0} bytes "
              f"in {time.time() - t0:.2f}s")
        return 0 if ok else 1

    print("\n[4] SPEAK")
    t0 = time.time()
    v.speak(text)
    if v._worker:
        v._worker.join(timeout=90)
    print(f"      finished in {time.time() - t0:.2f}s")
    return 0


def cancel_demo(v: V.Voice) -> int:
    """Show the generation counter: a new sentence kills the old one mid-flight."""
    print("\n[1] start a long sentence")
    long_text = ("Here is a very long answer that would take a while to say. " * 6)
    v.speak(long_text)
    time.sleep(1.2)

    print("[2] user interrupts: say something new")
    t0 = time.time()
    v.speak("Stopped. What do you need?")
    if v._worker:
        v._worker.join(timeout=30)
    print(f"    the second sentence finished in {time.time() - t0:.2f}s")
    bar()
    print("    The old worker checked the generation counter between chunks and")
    print("    returned. No queue, no overlap, nothing to clean up — `voice.stop()`")
    print("    does the same thing without starting a replacement.")
    return 0


def _wrap(text: str, width: int) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width) or [""]


if __name__ == "__main__":
    raise SystemExit(main())
