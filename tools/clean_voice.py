#!/usr/bin/env python3
"""Clean a clip so a voice clone comes out sounding like the person, not the room.

    python tools/clean_voice.py clip.mp3
    python tools/clean_voice.py clip.mp3 --out clean.wav --import --transcript "the words"

What it actually does, in order, with ffmpeg:

    1. highpass 80 Hz          remove rumble, desk thumps, mic handling
    2. afftdn                  spectral denoise — hiss, fan, air-conditioner, room tone
    3. silenceremove           trim leading/trailing silence so the model hears speech
    4. loudnorm I=-18 LUFS     match every clip to the same loudness
    5. 24 kHz mono 16-bit      what IndicF5 and XTTS expect

And it prints the **measured** before/after numbers, because "it sounds better" is
not a measurement: SNR is the gap between the quietest tenth and the loudest tenth of
the frames.

Honest limits — this tool will tell you which one bit you:

  * **Steady noise** (fan, hiss, hum, air-con) comes down a lot.
  * **A music bed is NOT noise** — it has the same spectral shape as a voice, so
    denoising cannot separate it. If the music is under the whole clip, the honest
    fix is source separation: `pip install demucs` and this tool will use it
    (`--two-stems=vocals`) when it is present. It is a 2 GB install.
  * **Reverb** (a big empty room) is not removable by any of this.
  * Denoising too hard makes a voice sound watery. `--strength` is capped for that
    reason; the default is deliberately gentle.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk import clone  # noqa: E402


def ffmpeg() -> str:
    """Bundled first (the installer ships it), then the environment."""
    from arcdesk import paths
    found = paths.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def demucs_available() -> bool:
    return bool(shutil.which("demucs") or _module("demucs"))


def _module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def separate_vocals(src: Path, work: Path) -> Path | None:
    """Take the music out when Demucs is installed. Returns the vocal stem, or None."""
    out = work / "stems"
    cmd = (["demucs"] if shutil.which("demucs")
           else [sys.executable, "-m", "demucs"])
    try:
        done = subprocess.run(cmd + ["--two-stems=vocals", "-o", str(out), str(src)],
                              capture_output=True, text=True, timeout=1800)
    except Exception:
        return None
    if done.returncode != 0:
        print("  demucs failed:", (done.stderr or "").strip()[-200:])
        return None
    for p in out.rglob("vocals*.wav"):
        return p
    return None


def clean(src: Path, out: Path, strength: float = 6.0, use_demucs: bool = False) -> dict:
    exe = ffmpeg()
    if not exe:
        return {"ok": False, "message": "ffmpeg is not installed — run install.bat "
                                        "(it is bundled with the one-click installer)"}
    work = Path(tempfile.mkdtemp(prefix="arcdesk-clean-"))
    stage = src
    used_demucs = False
    if use_demucs:
        if not demucs_available():
            print("  demucs is not installed — trying denoise alone.")
        else:
            print("  separating the vocal from the music (this takes as long as the clip)…")
            stem = separate_vocals(src, work)
            if stem:
                stage, used_demucs = stem, True

    nr = max(1.0, min(12.0, float(strength)))
    # Two passes on purpose: this ffmpeg build aborts ("Assertion best_input >= 0")
    # when `areverse` shares one filter graph with afftdn/highpass. Each half is
    # tested on its own, and a temp file between them costs nothing at this length.
    pass_one = work / "denoised.wav"
    chain_a = f"highpass=f=80,afftdn=nr={nr:.1f}:nf=-30:tn=1,loudnorm=I=-18:TP=-2:LRA=9"
    cmd_a = [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(stage),
             "-vn", "-ac", "1", "-ar", str(clone.SAMPLE_RATE), "-c:a", "pcm_s16le",
             "-af", chain_a, str(pass_one)]
    done = subprocess.run(cmd_a, capture_output=True, text=True, timeout=1800)
    if done.returncode != 0 or not pass_one.exists():
        return {"ok": False, "message": f"ffmpeg (denoise) failed: {(done.stderr or '')[-300:]}"}

    chain_b = ("silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,"
               "areverse,"
               "silenceremove=start_periods=1:start_silence=0.12:start_threshold=-45dB,"
               "areverse")
    cmd_b = [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(pass_one),
             "-vn", "-ac", "1", "-ar", str(clone.SAMPLE_RATE), "-c:a", "pcm_s16le",
             "-af", chain_b, str(out)]
    done = subprocess.run(cmd_b, capture_output=True, text=True, timeout=1800)
    if done.returncode != 0 or not out.exists():
        # the trim is cosmetic; a clip that cannot be trimmed is still cleaned
        shutil.copyfile(pass_one, out)
        return {"ok": True, "path": str(out), "demucs": used_demucs,
                "note": "edges not trimmed (ffmpeg refused that step)"}
    return {"ok": True, "path": str(out), "demucs": used_demucs}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Clean a voice clip before cloning it.")
    ap.add_argument("source")
    ap.add_argument("--out", default="")
    ap.add_argument("--strength", type=float, default=6.0,
                    help="denoise strength 1-12 (default 6; higher risks a watery voice)")
    ap.add_argument("--demucs", action="store_true",
                    help="separate vocals from music first (needs demucs installed)")
    ap.add_argument("--import", dest="do_import", action="store_true",
                    help="make the result ARC's clone reference")
    ap.add_argument("--transcript", default="", help="the words spoken in the clip")
    args = ap.parse_args(argv[1:])

    src = Path(args.source).expanduser()
    if not src.exists():
        print(f"no such file: {src}")
        return 2
    out = Path(args.out).expanduser() if args.out else (
        src.with_name(src.stem + "-clean.wav"))

    before = clone.analyse(src)
    print(f"\nBEFORE  {src.name}")
    _show(before)

    print("\ncleaning …")
    got = clean(src, out, args.strength, args.demucs)
    if not got["ok"]:
        print("  " + got["message"])
        return 1
    after = clone.analyse(out)
    print(f"\nAFTER   {out.name}" + ("   (vocals separated with demucs)" if got["demucs"] else ""))
    _show(after)

    print("\nchange")
    print(f"  background   {before['background_db']:>7.1f} → {after['background_db']:>7.1f} dB")
    print(f"  speech       {before['speech_db']:>7.1f} → {after['speech_db']:>7.1f} dB")
    print(f"  SNR          {before['snr_db']:>7.1f} → {after['snr_db']:>7.1f} dB")
    print(f"  length       {before['seconds']:>7.2f} → {after['seconds']:>7.2f} s")
    print(f"  grade        {before['grade']:>7} → {after['grade']}")

    music_bed = before["snr_db"] < 20 and not got["demucs"]
    if music_bed:
        print("\n  This clip had less than 20 dB between your voice and what is behind it.")
        print("  If that was MUSIC, denoising cannot remove it — music and voice overlap")
        print("  in the spectrum. Install the separator and run this again:")
        print("      pip install demucs")
        print(f"      python tools\\clean_voice.py \"{src.name}\" --demucs --import")
    elif after["snr_db"] - before["snr_db"] < 1.0:
        print("\n  Denoising barely changed the SNR — there was little steady noise to")
        print("  remove. That is a clean clip; do not clean it again, it only costs time.")

    if args.do_import:
        print("\nimporting as the clone reference …")
        got = clone.import_reference(str(out), args.transcript)
        print(("OK   " if got["ok"] else "FAIL ") + got["message"])
        if got["ok"]:
            print(f"     grade {got.get('grade')} · {got.get('seconds')} s · "
                  f"SNR {got.get('snr_db')} dB")
            print("     now: python tools\\voice_setup.py try \"vanakkam macha\"")
        return 0 if got["ok"] else 1
    print(f"\n  next: python tools\\voice_setup.py import \"{out}\"")
    return 0


def _show(a: dict) -> None:
    print(f"  length {a['seconds']:.2f} s · speech {a['speech_db']:.1f} dB · "
          f"background {a['background_db']:.1f} dB · SNR {a['snr_db']:.1f} dB · "
          f"clipped {a['clip_pct']:.2f}%")
    print(f"  grade {a['grade']} — {a['advice']}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
