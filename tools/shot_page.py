#!/usr/bin/env python3
"""Render the actual Jarvis page (the magic screen) to real files — proof, not a mockup.

    python tools/shot_page.py                      # 3 stills + a 5 s clip
    python tools/shot_page.py --frames 180 --seconds 6 --size 1920x1080
    python tools/shot_page.py --still-only

This is the page you get after "hey jarvis": the holographic deck as the surface,
with the app buttons, the input box and the exit hint floating on top of it. Every
pixel comes from `arcdesk.widgets.magicscreen` — the widget the app itself shows —
rendered offscreen, with this machine's real telemetry inside.
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
os.environ.setdefault("ARCDESK_HOME", str(Path("/tmp") / "arcdesk-page-shot"))

from PySide6.QtCore import QSize                    # noqa: E402
from PySide6.QtWidgets import QApplication          # noqa: E402

from arcdesk.theme import THEMES                    # noqa: E402
from arcdesk.widgets.magicscreen import MagicScreen  # noqa: E402

OUT = ROOT / "shots"
TYPED = "show me the hologram"


def build(size: QSize, theme_key: str) -> tuple[QApplication, MagicScreen]:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    page = MagicScreen(THEMES[theme_key], "bye jarvis")
    page.resize(size)
    page.show()
    return app, page


def render(size: QSize, theme_key: str, frames: int, still_only: bool) -> list[str]:
    app, page = build(size, theme_key)
    frames_dir = Path("/tmp/arcdesk_page_frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.png"):
        old.unlink()

    written: list[str] = []
    # the typing happens over the first second, so the clip shows the page waking up
    per_frame = 1 / 30.0
    stills_at = {24: "jarvis_page_typing", int(frames * 0.55): "jarvis_page",
                 int(frames * 0.88): "jarvis_page_live"}
    for i in range(frames):
        typed = min(len(TYPED), int(max(0, i - 12) * 0.55))
        page.input.setText(TYPED[:typed])
        if i == int(frames * 0.62):
            page.input.clear()
            page.set_status("MAGIC MODE ACTIVE · LISTENING")
        page.advance(per_frame)
        app.processEvents()
        pix = page.grab()
        if not still_only:
            pix.save(str(frames_dir / f"f{i:04d}.png"))
        if i in stills_at:
            name = stills_at[i]
            path = OUT / f"{name}.png"
            pix.save(str(path))
            written.append(str(path.relative_to(ROOT)))

    if not still_only:
        clip = OUT / "jarvis_page.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30",
               "-i", str(frames_dir / "f%04d.png"), "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(clip)]
        try:
            subprocess.run(cmd, check=True, timeout=300)
            written.append(str(clip.relative_to(ROOT)))
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"  no clip: {exc}")
    page.close()
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="render the Jarvis page offscreen")
    ap.add_argument("--size", default="1600x900")
    ap.add_argument("--theme", default="chill", choices=sorted(THEMES))
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--seconds", type=float, default=5.0, help="wall-clock budget hint")
    ap.add_argument("--still-only", action="store_true")
    args = ap.parse_args()

    w, h = (int(v) for v in args.size.lower().split("x"))
    t0 = time.time()
    print(f"ARC DESK · Jarvis page · {w}x{h} · theme={args.theme} · "
          f"{args.frames} frames @ 30 fps")
    for path in render(QSize(w, h), args.theme, args.frames, args.still_only):
        print(f"  wrote   {path}")
    print(f"done in {time.time() - t0:.1f}s — the page the app itself shows, "
          f"with this machine's real telemetry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
