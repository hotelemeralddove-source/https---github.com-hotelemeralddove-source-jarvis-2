"""CPU / RAM / own-footprint sampling.

psutil's cpu_percent(interval=None) is non-blocking: it compares against the
previous call instead of sleeping. Sampling happens once per second off a
QTimer, never inside a paint event, so it can never cause frame drops.
"""
from __future__ import annotations

import os

try:
    import psutil
except Exception:  # pragma: no cover - app still runs without psutil
    psutil = None


class SystemSampler:
    def __init__(self) -> None:
        self.cpu = 0.0
        self.ram = 0.0
        self.mem_used = 0
        self.mem_total = 0
        self.self_mb = 0.0
        self.cores = os.cpu_count() or 1
        self._proc = None
        if psutil is not None:
            try:
                self._proc = psutil.Process()
                self.mem_total = psutil.virtual_memory().total
                psutil.cpu_percent(interval=None)  # prime the delta window
                self._proc.cpu_percent(interval=None)
            except Exception:
                pass

    def sample(self) -> None:
        if psutil is None:
            return
        try:
            self.cpu = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            self.ram = vm.percent
            self.mem_used = vm.total - vm.available
            self.mem_total = vm.total
        except Exception:
            pass
        if self._proc is not None:
            try:
                self.self_mb = self._proc.memory_info().rss / (1024 * 1024)
            except Exception:
                pass


def fmt_gb(nbytes: int) -> str:
    return f"{nbytes / (1024 ** 3):.1f} GB"
