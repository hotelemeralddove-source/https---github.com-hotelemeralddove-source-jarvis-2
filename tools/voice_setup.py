#!/usr/bin/env python3
"""Voice setup — one command for "use MY voice" and "only MY voice wakes it".

    python tools/voice_setup.py status
    python tools/voice_setup.py import  C:\\path\\clip.mp4 --transcript "the words it says"
    python tools/voice_setup.py try     "vanakkam macha, ellam ready"
    python tools/voice_setup.py lock-enroll me  rec1.wav rec2.wav rec3.wav
    python tools/voice_setup.py lock-test  rec4.wav
    python tools/voice_setup.py lock-on | lock-off
    python tools/voice_setup.py lock-model          # download the 30 MB speaker model
    python tools/voice_setup.py selftest [--against other.wav]   # prove it works

Why a CLI: cloning and speaker-id are model problems, not GUI problems. This prints
exactly what is installed and what is missing, and each line says what to run next.
Nothing here downloads silently and nothing counts as "ready" until it runs.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk import clone, config, voiceid  # noqa: E402


def _line(k: str, v: str) -> None:
    print(f"  {k:<24} {v}")


def cmd_status(_argv: list[str] | None = None) -> int:
    plan = clone.plan()
    print("\nVOICE CLONE — speaking in the imported voice\n" + "=" * 66)
    for name, info in plan["engines"].items():
        state = "ready" if info["available"] else f"no — {info['why']}"
        _line(name, state)
    _line("promised", ", ".join(f"{c} → {e}" for c, e in
                                (("Tamil", "IndicF5"), ("Hindi", "IndicF5"),
                                 ("English", "XTTS"))))
    _line("reference clip", plan["reference"] or "none imported yet")
    if plan["reference"]:
        q = clone.quality()
        _line("reference length", f"{plan['reference_seconds']:g} s")
        _line("reference quality", f"{q['grade']} · SNR {q['snr_db']:g} dB · "
                                   f"background {q['background_db']:g} dB")
        _line("what to fix", q["advice"])
    _line("transcript saved", "yes" if plan["transcript"] else "no (IndicF5 needs it)")
    _line("Tamil goes to", clone.route("ta"))
    _line("Hindi goes to", clone.route("hi"))
    _line("English goes to", clone.route("en"))

    print("\nVOICE LOCK — who may command it on THIS machine\n" + "=" * 66)
    ok, why = voiceid.available()
    _line("engine", voiceid.engine()["name"] or f"none — {why}")
    profiles = voiceid.profiles()
    if profiles:
        for name, p in profiles.items():
            _line(f"enrolled '{name}'", f"{p['samples']} clips · mean similarity "
                                        f"{p.get('self_similarity', 0):.2f} · "
                                        f"threshold {p.get('threshold', 0):.2f}")
    else:
        _line("enrolled", "nobody — anyone can wake it")
    _line("enabled in settings", "yes" if config.load()["wake"].get("voice_lock") else "no")

    print("\nWhat is honestly NOT possible for free, on this machine:\n")
    for limit in plan["limits"]:
        print(f"  · {limit}")
    print("\nNext: `python tools/voice_setup.py import <file>` then `try \"hello\"`.\n")
    return 0


def cmd_import(argv: list[str]) -> int:
    if not argv:
        print("usage: voice_setup.py import <audio-or-video> [--transcript \"words\"]")
        return 2
    src = argv[0]
    transcript = ""
    if "--transcript" in argv:
        transcript = argv[argv.index("--transcript") + 1]
    got = clone.import_reference(src, transcript)
    print(("OK   " if got["ok"] else "FAIL ") + got["message"])
    if got["ok"]:
        print(f"     {got['path']} · {got['seconds']:g} s")
        print("     now: python tools/voice_setup.py try \"vanakkam macha\"")
    return 0 if got["ok"] else 1


def cmd_try(argv: list[str]) -> int:
    text = " ".join(argv) or "vanakkam macha, ellam ready"
    lang = clone.route(_guess_lang(text))
    print(f"engine: {lang} · text: {text}")
    if lang in ("piper", "sapi"):
        print("no clone engine yet — this will come out in the fallback voice.")
        print("install one:  install_clone.bat   (IndicF5 for Tamil/Indic, XTTS for English)")
    from arcdesk.ai.voice import Voice
    v = Voice(config.load())
    v.speak(text)
    import time
    time.sleep(0.5)
    while v.speaking:
        time.sleep(0.1)
    return 0


def _guess_lang(text: str) -> str:
    try:
        from arcdesk import lang as langmod
        return langmod.detect(text)
    except Exception:
        return "en"


def cmd_lock_enroll(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: voice_setup.py lock-enroll <name> <rec1.wav> <rec2.wav> [rec3.wav]")
        print("      3 recordings of YOU, 3-8 s each, quiet room, normal speaking voice.")
        return 2
    name, wavs = argv[0], argv[1:]
    got = voiceid.enroll(name, wavs)
    print(("OK   " if got["ok"] else "FAIL ") + got["message"])
    if got["ok"]:
        print(f"     self-similarity {got['self_similarity']:.2f} (higher is better; "
              f"under 0.55 means the clips disagree — record again)")
        print(f"     threshold {got['threshold']:.2f}")
    return 0 if got["ok"] else 1


def cmd_lock_test(argv: list[str]) -> int:
    if not argv:
        print("usage: voice_setup.py lock-test <recording.wav>")
        return 2
    got = voiceid.verify(argv[0])
    print(f"{'ALLOWED' if got['allowed'] else 'REJECTED'}  "
          f"who={got['who'] or '-'}  score={got['score']:.2f}"
          + (f"  needed={got['needed']:.2f}" if "needed" in got else ""))
    if got.get("why"):
        print("  " + got["why"])
    return 0 if got["allowed"] else 1


def cmd_selftest(argv: list[str]) -> int:
    """Prove the voice lock works — with real audio, on this machine.

    Splits the imported reference into three takes plus a held-out take, enrols a
    SCRATCH profile, then checks the held-out take (must pass). With `--against
    other.wav` it also checks somebody else's recording (must fail). The scratch
    profile is removed afterwards, so this never becomes your real enrolment.
    """
    import subprocess
    import tempfile
    from pathlib import Path as _Path

    ok, why = voiceid.available()
    if not ok:
        print("cannot self-test: " + why)
        return 1
    ref = clone.reference()
    if not ref:
        print("import a reference clip first: python tools\\voice_setup.py import <file>")
        return 1
    exe = _ffmpeg()
    if not exe:
        print("ffmpeg is needed to split the clip into takes")
        return 1

    seconds = clone.analyse(ref)["seconds"]
    if seconds < 6:
        print(f"the reference is only {seconds:.1f} s — 8 s or more is needed to split it "
              f"into three takes and a held-out one")
        return 1

    work = _Path(tempfile.mkdtemp(prefix="arcdesk-selftest-"))
    span = (seconds - 0.6) / 4.0
    takes = []
    for i in range(4):
        out = work / f"take{i}.wav"
        subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{i * span:.2f}", "-t", f"{span:.2f}", "-i", str(ref),
                        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)],
                       check=False)
        takes.append(str(out))

    got = voiceid.enroll("__selftest__", takes[:3])
    if not got["ok"]:
        print("FAIL " + got["message"])
        return 1
    try:
        same = voiceid.verify(takes[3])
        print(f"\nSELF-TEST with {seconds:.1f} s of this voice")
        print(f"  three takes enrolled      : yes ({got['samples']})")
        print(f"  they agree                : {got['self_similarity']:.2f}")
        print(f"  held-out take (same voice): {'PASS' if same['allowed'] else 'FAIL'}"
              f"  score {same['score']:.2f} (needs {same.get('needed', 0):.2f})")
        ok_all = bool(same["allowed"])
        if "--against" in argv:
            other = argv[argv.index("--against") + 1]
            diff = voiceid.verify(other)
            print(f"  another voice ({_Path(other).name}) : "
                  f"{'correctly REJECTED' if not diff['allowed'] else 'WRONGLY ACCEPTED'}"
                  f"  score {diff['score']:.2f}")
            ok_all &= not diff["allowed"]
        else:
            print("  another voice             : not tested (add --against other.wav)")
        return 0 if ok_all else 1
    finally:
        voiceid.forget("__selftest__")
        print("  scratch profile removed   : yes")


def _ffmpeg() -> str:
    from arcdesk import paths
    if paths.which("ffmpeg"):
        return paths.which("ffmpeg")
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def cmd_lock_toggle(on: bool) -> int:
    cfg = config.load()
    cfg.setdefault("wake", {})["voice_lock"] = on
    config.save(cfg)
    if on and not voiceid.profiles():
        print("enabled in settings, but nobody is enrolled — it will not block anyone "
              "until you run `lock-enroll`.")
    if on:
        ok, why = voiceid.available()
        if not ok:
            print(f"warning: {why}")
    print(f"voice lock {'ON' if on else 'OFF'} (restart the wake word to apply)")
    return 0


def cmd_lock_model() -> int:
    """Download the small speaker-embedding model, visibly."""
    print(f"downloading {voiceid.SPEAKER_MODEL_URL.rsplit('/', 1)[-1]} …")
    got = voiceid.download_model(progress=lambda pct: print(f"  {pct}%", end="\r"))
    print()
    print(("OK   " if got["ok"] else "FAIL ") + got["message"])
    return 0 if got["ok"] else 1


def main(argv: list[str]) -> int:
    cmd = (argv[1] if len(argv) > 1 else "status").lower()
    rest = argv[2:]
    table = {
        "status": cmd_status,
        "import": cmd_import,
        "try": cmd_try,
        "lock-enroll": cmd_lock_enroll,
        "lock-test": cmd_lock_test,
        "lock-model": lambda a: cmd_lock_model(),
        "selftest": cmd_selftest,
        "lock-on": lambda a: cmd_lock_toggle(True),
        "lock-off": lambda a: cmd_lock_toggle(False),
    }
    fn = table.get(cmd)
    if not fn:
        print(__doc__)
        return 2
    return fn(rest)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
