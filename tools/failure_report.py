#!/usr/bin/env python3
"""Turn a red check.bat into one file that says what failed, in words.

    python tools/failure_report.py            # print the failing lines
    python tools/failure_report.py --write    # …and write check-report.txt next to it

Why: the screenshot of `check.bat` (27.png) shows the summary only —

    FAIL  test_app_lifecycle   0.0s
    FAIL  test_backup          1.2s

— and the reason lives one level down in `.failures\\<test>.txt`, which nobody opens on a
laptop where the folder is behind a terminal. So the reasons are lifted out, printed in the
same window, and copied into a single small text file that can be sent as it is.

Nothing in the file is personal: versions, the folder name, and the failing lines.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAIL_DIR = ROOT / ".failures"
REPORT = ROOT / "check-report.txt"
MAX_LINES_PER_TEST = 6


def _free_gb(path: Path) -> str:
    try:
        return f"{shutil.disk_usage(str(path)).free / 1024 ** 3:.1f} GB free"
    except Exception:                                            # noqa: BLE001
        return "free space unknown"


def _failing(name: str, text: str) -> list[str]:
    """The lines worth reading: the FAIL lines, else the last exception in the block."""
    out = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("FAIL")
           or re.match(r"^\s*FAIL\b", ln)]
    if out:
        return out[:MAX_LINES_PER_TEST]
    tail = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    boom = [i for i, ln in enumerate(tail) if "Error" in ln or "Traceback" in ln]
    if boom:
        start = max(0, boom[-1] - 2)
        return [ln.strip() for ln in tail[start:start + MAX_LINES_PER_TEST]]
    return [ln.strip() for ln in tail[-MAX_LINES_PER_TEST:]]


def collect() -> tuple[str, bool]:
    """(the report as text, whether anything actually failed)."""
    rows: list[str] = []
    add = rows.append
    add("JARVIS check report")
    add("===================")
    add(f"when       : {platform.platform()}")
    add(f"python     : {sys.version.split()[0]} ({sys.executable})")
    add(f"folder     : {ROOT}")
    add(f"disk       : {_free_gb(ROOT)}")
    add("")

    failed = 0
    tests = sorted(FAIL_DIR.glob("*.txt")) if FAIL_DIR.is_dir() else []
    for path in tests:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            add(f"{path.stem}: could not be read ({exc})")
            failed += 1
            continue
        name = path.stem
        lines = _failing(name, text)
        if not lines:
            continue
        failed += 1
        add(f"{name}")
        for line in lines:
            add(f"    {line}")
        add("")

    if not tests:
        add("no .failures folder — nothing failed, or the check that failed was not "
            "tests\\run_all.py (a section before [3/9] reports its own reason on screen).")
        add("")

    log = Path(os.environ.get("APPDATA") or Path.home()) / "ArcDesk" / "logs" / "arcdesk.log"
    add(f"last app log ({log})")
    try:
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
        add("\n".join("    " + ln for ln in tail) if tail else "    (empty)")
    except OSError:
        add("    (no log — the app has not started from this folder yet)")
    add("")
    # A native crash (the app closed by itself) prints nothing a person can read. That is
    # the report this section exists for: "yethavathu select pana application crash aagi,
    # close aaguthu". If the last run left a fault log or a crash bundle, it goes in here.
    for name in ("crash-report.txt", "logs\\fault.log"):
        extra = Path(os.environ.get("APPDATA") or Path.home()) / "ArcDesk" / name
        if not extra.exists():
            continue
        add(f"crash evidence ({extra})")
        try:
            tail = extra.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
            add("\n".join("    " + ln for ln in tail))
        except OSError:
            add("    (could not be read)")
        add("")
    add("Send this whole file. It has no personal data in it: versions, the folder name, "
        "and the failing lines only.")
    return "\n".join(rows), failed > 0


def main(argv: list[str]) -> int:
    text, failed = collect()
    print()
    print(text)
    if "--write" in argv:
        try:
            REPORT.write_text(text + "\n", encoding="utf-8")
            print(f"\n  written: {REPORT}")
        except OSError as exc:
            print(f"\n  could not write {REPORT} ({exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
