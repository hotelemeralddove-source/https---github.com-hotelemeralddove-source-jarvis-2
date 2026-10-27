#!/usr/bin/env python3
"""Scan this PC for every open-source package Arc Desk can drive.

    python tools/github_scan.py             # what is here, grouped by role
    python tools/github_scan.py --all       # the whole catalogue, installed or not
    python tools/github_scan.py --json      # machine readable
    python tools/github_scan.py --plan      # paste-able commands for what is missing

Read-only: it opens TCP sockets to localhost, asks the OS for a command name, and
tries an import. It never installs, never connects to the internet, never writes.
Exit code is 0 unless the catalogue itself is inconsistent (then 2).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk.ai.catalog import CATALOG, REFUSED, ROLES, Package, summary  # noqa: E402
from arcdesk.ai.packages import detect as _detect, scan as _scan  # noqa: E402

GREEN, DIM, BOLD, RESET = "\033[32m", "\033[2m", "\033[1m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    GREEN = DIM = BOLD = RESET = ""          # old consoles: no ANSI games


def detect(p: Package):
    """Thin wrapper: the real detector lives in arcdesk/ai/packages.py, so the app
    and this script can never disagree about what is installed."""
    return _detect(p)


def scan():
    return _scan()


def print_table(rows: list[tuple[Package, bool | None]], show_all: bool) -> None:
    counts = summary()
    print(f"{BOLD}Arc Desk · open-source stack on this PC{RESET}")
    print("=" * 74)
    print(f"{counts['total']} GitHub packages catalogued · {counts['wired']} wired into Arc Desk")
    print(f"{counts['open_source']} open source · 1 freeware (listed for honesty)\n")

    for role, label in ROLES.items():
        group = [(p, st) for p, st in rows if p.role == role]
        if not show_all:
            group = [(p, st) for p, st in group if st]
        if not group:
            continue
        print(f"{BOLD}{role.upper()}{RESET}  {DIM}{label}{RESET}")
        for p, st in group:
            if st is True:
                mark = f"{GREEN}[found]{RESET}"
            elif st is False:
                mark = f"{DIM}[  -  ]{RESET}"
            else:
                mark = f"{DIM}[ info ]{RESET}"
            wired = "*" if p.arc_uses else " "
            print(f"  {mark}{wired} {p.name:<26} {p.licence:<22} {p.job[:58]}")
            if st is False and p.install:
                print(f"        {DIM}→ {p.install}{RESET}")
        print()

    found = sum(1 for _, st in rows if st is True)
    present = sum(1 for _, st in rows if st is not None)
    print(f"detected {found} of {present} checkable packages   (* = Arc Desk drives it today)")


def print_plan(rows: list[tuple[Package, bool | None]]) -> None:
    missing = [(p, st) for p, st in rows if st is False and p.install]
    if not missing:
        print("nothing missing — every checkable package is already installed.")
        return
    print(f"{BOLD}Paste these to fill the gaps (all free, no account, no card){RESET}")
    print("=" * 74)
    for p, _ in missing:
        print(f"{p.name}  ({p.role}, {p.licence})")
        print(f"  {p.install}")
        if p.url:
            print(f"  {DIM}{p.url}{RESET}")
        print()
    print(f"{BOLD}One-line upgrade that matters most:{RESET} "
          "Ollama for the brain, sherpa-onnx for ears+voice+wake.")


def main() -> int:
    ap = argparse.ArgumentParser(description="detect open-source AI packages")
    ap.add_argument("--all", action="store_true", help="show every catalogued package")
    ap.add_argument("--json", action="store_true", help="machine readable output")
    ap.add_argument("--plan", action="store_true", help="print install commands for gaps")
    ap.add_argument("--role", default="", help="filter by role, e.g. brain, see, recall")
    ap.add_argument("--md", default="", metavar="PATH",
                    help="regenerate the GITHUB.md tables from the catalogue")
    args = ap.parse_args()

    from arcdesk.ai.catalog import check
    problems = check()
    if problems:
        print("catalogue is inconsistent:", *problems, sep="\n  ")
        return 2

    if args.md:
        from github_scan_md import write_markdown
        path = write_markdown(args.md)
        print(f"wrote {path} from {len(CATALOG)} catalogue rows")
        return 0

    rows = scan()
    if args.role:
        rows = [(p, st) for p, st in rows if p.role == args.role]

    if args.json:
        print(json.dumps(
            [{"key": p.key, "name": p.name, "role": p.role, "repo": p.repo,
              "licence": p.licence, "url": p.url, "found": st,
              "wired": p.arc_uses, "install": p.install, "job": p.job}
             for p, st in rows], indent=2))
        return 0

    print_table(rows, show_all=args.all)
    if args.plan:
        print()
        print_plan(rows)
    if args.all:
        print(f"\n{BOLD}deliberately not used{RESET}")
        for name, why in REFUSED:
            print(f"  ✗ {name}\n    {DIM}{why}{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
