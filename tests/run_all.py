#!/usr/bin/env python3
"""Run every test with the right environment, in one command.

    python tests/run_all.py            # all tests
    python tests/run_all.py magic docs # only those whose name contains it

Why this file exists: five of the tests need ``QT_QPA_PLATFORM=offscreen`` and all
of them should run against a throw-away settings folder. Running them by hand
without that produced *silence* instead of a failure, which is worse than a red
test. Now there is exactly one way to validate the build, and it cannot be
forgotten.

Exit code 0 only when every test passed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = sorted(p for p in (ROOT / "tests").glob("test_*.py"))


FAILED_OUT: dict[str, str] = {}
FAIL_DIR = ROOT / ".failures"


def main(argv: list[str]) -> int:
    wanted = argv[1:]
    picked = [p for p in TESTS if not wanted or any(w in p.stem for w in wanted)]
    if not picked:
        print(f"no test matches {wanted}")
        return 2

    if FAIL_DIR.exists():                      # a stale log is worse than none
        for stale in FAIL_DIR.glob("*.txt"):
            stale.unlink()
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"      # no display needed, ever
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("ARCDESK_HOME", None)             # each test makes its own sandbox

    print(f"Arc Desk · {len(picked)} tests")
    print("=" * 62)
    results: list[tuple[str, str, float, str]] = []
    started = time.time()
    for path in picked:
        t0 = time.time()
        # encoding="utf-8" is not optional. On Windows the default is the ANSI code
        # page (cp1252), and the first test that prints a user-visible dash or arrow
        # raised UnicodeDecodeError inside the reader thread — leaving proc.stdout as
        # None, which then crashed the *runner* with "argument of type 'NoneType' is
        # not iterable". On GitHub's Windows runner that failed the build at test 13.
        proc = subprocess.run([sys.executable, str(path)], cwd=str(ROOT), env=env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300)
        out = proc.stdout or ""          # None if the child produced nothing readable
        err = proc.stderr or ""
        # A test that could not run (e.g. its port is taken) exits 0 and says SKIP.
        # That is not a pass and must never be reported as one.
        if proc.returncode == 0 and "SKIP" in out and "PASS" not in out:
            status = "SKIP"
        elif proc.returncode == 0 and ("PASS" in out or "ALL PASS" in out):
            status = "PASS"
        else:
            status = "FAIL"
        tail = (out.strip().splitlines() or [""])[-1]
        if status == "FAIL" and not tail.strip():
            tail = (err.strip().splitlines() or ["(no output)"])[-1]
        results.append((path.stem, status, time.time() - t0, tail if status == "FAIL" else ""))
        if status == "FAIL":
            # The summary line says WHICH test failed; this says WHY. Two things go into
            # the file: the assertions that actually failed (with a few lines of context,
            # because "FAIL it finished  'failed'" means nothing without it) and the tail
            # of the output. The first Windows run showed only a heading — useless.
            body = out or ""
            lines = body.splitlines()
            failing: list[str] = []
            for i, line in enumerate(lines):
                if "FAIL" in line:
                    failing.extend(lines[max(0, i - 2):i + 6])
                    failing.append("")
            report = [f"# {path.stem} — FAIL", ""]
            if failing:
                report += ["## the failing checks (with context)", "```"]
                report += failing[:80]
                report += ["```", ""]
            if err.strip():
                report += ["## stderr / traceback", "```", *err.strip().splitlines()[-40:],
                           "```", ""]
            report += ["## last 40 lines of output", "```", *lines[-40:], "```"]
            text = "\n".join(report)
            kept = "\n".join([*(failing[:12] or []), *lines[-12:]]) or "(no output)"
            FAILED_OUT[path.stem] = kept
            (FAIL_DIR).mkdir(exist_ok=True)
            (FAIL_DIR / f"{path.stem}.txt").write_text(text, encoding="utf-8")
        print(f"{status}  {path.stem:<26} {time.time() - t0:5.1f}s"
              f"{'  ' + tail[:60] if status == 'FAIL' else ''}")

    passed = sum(1 for _, st, _, _ in results if st == "PASS")
    skipped = sum(1 for _, st, _, _ in results if st == "SKIP")
    failed = [n for n, st, _, _ in results if st == "FAIL"]
    print("=" * 62)
    print(f"{passed}/{len(results)} passed in {time.time() - started:.1f}s"
          + (f" · {skipped} skipped" if skipped else ""))
    if failed:
        print("FAILED:", ", ".join(failed))
        print()
        for name in failed:
            print(f"----- {name} (last 12 lines) -----")
            body = FAILED_OUT.get(name) or "(no output captured)"
            for line in body.splitlines():
                print("   ", line)
            print()
        print(f"full logs: {FAIL_DIR}")
        return 1
    print("RESULT: everything passes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
