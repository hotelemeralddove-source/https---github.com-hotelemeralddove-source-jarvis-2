"""Lint the .bat files, because cmd.exe is a language with no compiler.

A `.bat` that is wrong does not raise: it prints "was unexpected at this time" and exits,
or worse, silently skips half a block. The two mistakes that keep appearing in this repo:

  1. **a bare `(` or `)` inside an `echo`** — cmd parses the parenthesis as the end of the
     surrounding `if (...)` block, so the rest of the block becomes garbage,
  2. **a `goto :label` with no matching `:label`** — the script stops, quietly.

And one that matters for trust: a diagnostic that runs on somebody's PC must not quietly
change things. So the checker also refuses `setx`, `set-executionpolicy`, `reg add`,
`netsh` and `schtasks /create` in a file that is supposed to only *look*.

    python tools\\batlint.py                # every .bat in the repo
    python tools\\batlint.py ArcDeskDiag.bat

Exit code 0 when every file is clean.
"""
from __future__ import annotations

import re

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Commands a read-only diagnostic must never run.
FORBIDDEN = ("setx ", "set-executionpolicy", "reg add", "netsh ", "schtasks /create",
             "bcdedit", "takeown", "icacls", "format ")

_ECHO = re.compile(r'^(?P<red>>>?"[^"]*"\s+)?echo', re.I)


def lint(path: Path, read_only: bool = False) -> list[str]:
    """Return one problem per line. An empty list means cmd will not trip over it."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"cannot read: {exc}"]

    problems: list[str] = []
    depth = 0
    labels: set[str] = set()
    gotos: list[str] = []

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.lower().startswith(("rem", "::", "@rem")):
            continue

        if stripped.startswith(":"):
            labels.add(re.split(r"[\s,]", stripped[1:])[0].lower())
            continue

        match = re.match(r"goto\s+:?(\w+)", stripped, re.I)
        if match:
            gotos.append(match.group(1).lower())

        # 1. a parenthesis inside an echo only bites when it is inside a block: there,
        #    cmd treats it as the end of the block and the rest of the script is garbage.
        #    At the top level `echo (optional)` is perfectly fine, so flagging it would
        #    just teach everyone to ignore this checker.
        if depth > 0 and _ECHO.match(stripped):
            body = _ECHO.sub("", stripped)
            if "(" in body.replace("^(", "") or ")" in body.replace("^)", ""):
                problems.append(f"{path.name}:{number} bare parenthesis in an echo inside "
                                f"a block — cmd ends the block here")

        # 2. block balance. Parens are only structural outside an echo, so an echo line
        #    never moves the counter — otherwise `echo (optional)` at the top level would
        #    look like an opened block and every line after it would be misjudged.
        if not _ECHO.match(stripped):
            bare = re.sub(r'\^[()]', "", re.sub(r'"[^"]*"', '""', stripped))
            depth += bare.count("(") - bare.count(")")
            if depth < 0:
                problems.append(f"{path.name}:{number} a block closes that was never opened")
                depth = 0

        # 3. a diagnostic that only looks must only look
        if read_only:
            low = stripped.lower()
            for command in FORBIDDEN:
                if command in low and not low.startswith(("echo", "rem")):
                    problems.append(f"{path.name}:{number} runs {command.strip()!r} — "
                                    f"this file is supposed to change nothing")

    if depth != 0:
        problems.append(f"{path.name} ends with {depth} unclosed block(s)")
    for target in gotos:
        if target not in labels and target not in {"eof"}:
            problems.append(f"{path.name} jumps to :{target}, which does not exist")
    # ---- a quoted %~dp0 passed to a real command ---------------------------
    # IT ENDS WITH A BACKSLASH. `robocopy "%~dp0" "%PROJ%"` becomes
    # `"C:\...\pack\" "%PROJ%"`, the trailing \ escapes its own closing quote, and the
    # whole line arrives as ONE argument:
    #     ERROR : Invalid Parameter #1 : "C:\...\arcdesk-fix45-..."      (17.png)
    # `cd /d "%~dp0"`, `pushd`, `call :label "%~dp0"` and `if exist "%~dp0..."` are fine:
    # they are not handing it to a program that parses quotes.
    safe_starts = ("cd ", "cd/d", "pushd", "call :", "if exist", "if not exist")
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped.lower().startswith(("robocopy", "xcopy", "copy ", "move ",
                                            "python", "powershell", "start ")):
            continue
        if '"%~dp0"' in stripped:
            problems.append(
                f"{path.name}:{number} passes \"%~dp0\" (it ends in a backslash) as an "
                f"argument — the closing quote is escaped and the command gets one "
                f"argument. Use set SRC=%~dp0, strip the last character, pass \"%SRC%\"")
    return problems


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    files = ([Path(a) for a in argv] if argv
             else sorted(p for p in ROOT.rglob("*.bat")
                         if not any(part in {".venv", "dist", "build", "node_modules"}
                                    for part in p.parts)))
    bad = 0
    for path in files:
        read_only = "diag" in path.name.lower()
        problems = lint(path, read_only=read_only)
        if problems:
            bad += 1
            print(f"[FAIL] {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
            for line in problems:
                print("       " + line)
        else:
            print(f"[ok]   {path.name}")
    print()
    print(f"{len(files) - bad}/{len(files)} batch files clean")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
