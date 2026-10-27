"""Dev helper: measure Arc Desk's own CPU and RAM footprint.

    QT_QPA_PLATFORM=offscreen python tools/bench.py --seconds 20

Runs the real window in a loop, samples this process once a second and
prints avg/max. Offscreen numbers are a floor: on a real Windows desktop
add roughly 20-40 MB for the DWM/compositor path.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk import config  # noqa: E402
from arcdesk.widgets.window import MainWindow  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--mode", default="chill")
    ap.add_argument("--size", default="1000x668")
    args = ap.parse_args()

    cfg = config.load()
    cfg["mode"] = args.mode
    w, h = (int(v) for v in args.size.lower().split("x"))
    cfg["window"] = {"w": w, "h": h, "x": 40, "y": 40}

    app = QApplication(sys.argv[:1])
    win = MainWindow(cfg)
    win.show()
    for _ in range(20):
        app.processEvents()

    proc = psutil.Process()
    proc.cpu_percent(None)
    cpu, rss = [], []
    t0 = time.time()
    while time.time() - t0 < args.seconds:
        app.processEvents()
        time.sleep(0.02)
        cpu.append(proc.cpu_percent(None))
        rss.append(proc.memory_info().rss / (1024 * 1024))

    # idle floor: what the app costs when animations are paused
    win.set_animations(False)
    time.sleep(0.4)
    proc.cpu_percent(None)
    idle = []
    t0 = time.time()
    while time.time() - t0 < 3.0:
        app.processEvents()
        time.sleep(0.01)
        idle.append(proc.cpu_percent(None))

    print(f"mode={args.mode} size={w}x{h}")
    print(f"  cpu  avg {statistics.mean(cpu):5.2f}%   max {max(cpu):5.2f}%")
    print(f"  rss  avg {statistics.mean(rss):5.1f} MB  max {max(rss):5.1f} MB")
    print(f"  idle (animations paused) cpu avg {statistics.mean(idle):5.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
