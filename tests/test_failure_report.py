"""When check.bat goes red, the reason must be on the screen — not in a folder.

    python tests/test_failure_report.py

The screenshot (27.png) shows only this:

    FAIL  test_app_lifecycle   0.0s
    FAIL  test_backup          1.2s

Which is a list of names, not an answer. The reasons live in `.failures\\<test>.txt`, so
`tools/failure_report.py` lifts them into the same window and into one small file. These
checks are about that file being honest: it must quote the real failing lines, must not
invent failures when nothing failed, and must not carry anything personal.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import failure_report                                        # noqa: E402

ok = True


def check(name: str, got, want=True) -> None:
    global ok
    good = got == want
    ok = ok and good
    print(f"   {'OK  ' if good else 'FAIL'} {name:<58} {got!r}")


print("1. the failing lines are what it finds")
sample = """# test_app_lifecycle — FAIL

## the failing checks (with context)
```
   OK   the app starts                                  True
   FAIL it reaches the lock within 5 s                  False
   FAIL it says why in the log                          'nothing'
```
"""
lines = failure_report._failing("test_app_lifecycle", sample)            # noqa: SLF001
check("both FAIL lines, and nothing else", len(lines), 2)
check("…verbatim, with the measured value", "False" in lines[0], True)

print("\n2. a crash with no FAIL line still gets an answer")
boom = "Traceback (most recent call last):\n  File x.py\nValueError: no such value\n"
lines = failure_report._failing("test_clone", boom)                      # noqa: SLF001
check("the exception is quoted", any("ValueError" in ln for ln in lines), True)

print("\n3. nothing failed means nothing is invented")
check("an empty file yields no lines", failure_report._failing("x", ""), [])
before = failure_report.FAIL_DIR
failure_report.FAIL_DIR = Path(tempfile.mkdtemp(prefix="arcdesk-noffail-"))
text, failed = failure_report.collect()
failure_report.FAIL_DIR = before
check("it does not claim a failure", failed, False)
check("…and says why there is nothing", "no .failures folder" in text, True)

print("\n4. what the report carries")
text, _ = failure_report.collect()
check("the platform", "when" in text, True)
check("the python in use", "python" in text.lower(), True)
check("the folder it checked", str(ROOT) in text, True)
check("the app's last log lines", "last app log" in text, True)
check("small enough to send in one message", len(text) < 8000, True)

print("\n5. it is wired into the red branch of check.bat")
bat = (ROOT / "check.bat").read_bytes().decode("ascii")
check("check.bat writes the file", "failure_report.py --write" in bat, True)
check("…and tells the person to send it", "send that one file" in bat, True)
check("…and no longer says 'a screenshot is enough'",
      "screenshot is enough" in bat, False)
proc = subprocess.run([sys.executable, str(ROOT / "tools" / "failure_report.py")],
                      capture_output=True, text=True, timeout=120,
                      cwd=str(ROOT))
check("running it directly works", proc.returncode, 0)
check("…and prints a report", "JARVIS check report" in (proc.stdout or ""), True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
