#!/usr/bin/env python3
"""Render the holographic deck to real files — proof, not a mockup.

    python tools/shot_holo.py                 # 3 stills + a 6 s clip
    python tools/shot_holo.py --frames 120 --seconds 6 --size 1600x900
    python tools/shot_holo.py --still-only

Everything is painted by the same widget the app uses (`arcdesk.widgets.holo`),
offscreen, with the real machine's telemetry inside it. The clip is encoded with
ffmpeg when it is available; without ffmpeg you still get the stills and a
truthful note saying why there is no video.

Why offscreen works: `QT_QPA_PLATFORM=offscreen` gives a real raster surface with
no display, so the frames are produced by the identical paint code path.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ARCDESK_HOME", str(Path("/tmp") / "arcdesk-holo-shot"))

from PySide6.QtCore import QSize                    # noqa: E402
from PySide6.QtWidgets import QApplication          # noqa: E402

from arcdesk.theme import THEMES                    # noqa: E402
from arcdesk.widgets.holo import HoloDeck           # noqa: E402

OUT = ROOT / "shots"


def render(size: QSize, theme_key: str, frames: int, stills: int) -> list[str]:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    deck = HoloDeck(THEMES[theme_key])
    deck.resize(size)
    deck.show()
    app.processEvents()

    OUT.mkdir(exist_ok=True)
    written: list[str] = []
    frame_dir = Path("/tmp") / "arcdesk-holo-frames"
    frame_dir.mkdir(exist_ok=True)
    for old in frame_dir.glob("f_*.png"):
        old.unlink()

    grab_every = max(1, frames // max(1, stills))
    for i in range(frames):
        # advance the animation deterministically: one tick is one frame
        deck._on_tick(1 / 30.0)                      # noqa: SLF001 — this is its renderer
        app.processEvents()
        pix = deck.grab()
        if i % grab_every == 0 and len(written) < 20:
            name = f"holo_{theme_key}_{i:03d}.png"
            pix.save(str(frame_dir / f"f_{i:04d}.png"))
            written.append(name)
        else:
            pix.save(str(frame_dir / f"f_{i:04d}.png"))
    return written


def encode(frame_dir: Path, out_mp4: Path, fps: int) -> str:
    exe = None
    for name in ("ffmpeg", "ffmpeg.exe"):
        from shutil import which
        exe = which(name)
        if exe:
            break
    if not exe:
        return "ffmpeg not found — stills only (winget install Gyan.FFmpeg)"
    cmd = [exe, "-y", "-v", "error", "-framerate", str(fps), "-i",
           str(frame_dir / "f_%04d.png"), "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart",
           str(out_mp4)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0 or not out_mp4.exists():
        tail = (res.stderr or "").strip().splitlines()[-2:]
        return "ffmpeg failed: " + " | ".join(tail)
    return f"{out_mp4.name} ({out_mp4.stat().st_size / 1e6:.1f} MB)"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="1600x900")
    ap.add_argument("--theme", default="chill", choices=sorted(THEMES))
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--still-only", action="store_true")
    args = ap.parse_args(argv[1:])

    w, h = (int(x) for x in args.size.lower().split("x"))
    fps = max(12, int(args.frames / max(0.5, args.seconds)))
    print(f"ARC DESK · hologram deck · {w}x{h} · theme={args.theme} · "
          f"{args.frames} frames @ {fps} fps")

    t0 = time.time()
    render(QSize(w, h), args.theme, args.frames, 3)
    frame_dir = Path("/tmp") / "arcdesk-holo-frames"

    stills = sorted(frame_dir.glob("f_*.png"))
    # three representative stills: boot, mid, steady state
    picks = [stills[0], stills[len(stills) // 3], stills[-1]]
    for label, src in zip(("boot", "live", "steady"), picks):
        dst = OUT / f"holo_{label}.png"
        dst.write_bytes(src.read_bytes())
        print(f"  still   {dst.relative_to(ROOT)}")

    if not args.still_only:
        msg = encode(frame_dir, OUT / "holo_deck.mp4", fps)
        print(f"  clip    {msg}")

    print(f"done in {time.time() - t0:.1f}s — every pixel painted by the app's own "
          f"widget, with this machine's real telemetry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
