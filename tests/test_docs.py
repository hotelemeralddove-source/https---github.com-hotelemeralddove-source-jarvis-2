"""Docs must match the code. This is the test that catches "the README lied".

Three failure modes it blocks, all of which had already happened:

  1. a count drifts (24 tools became "21 tools" in four files while the code grew)
  2. a file is renamed or deleted and the docs keep pointing at it
  3. a claim about money creeps back in ("subscription", "free trial", ...)

Run:  python tests/test_docs.py
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import os

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk.ai import cost, tools  # noqa: E402

# The root keeps the handful of docs a person opens first (README, INSTALL, TROUBLESHOOT,
# CAPABILITIES, ONE-FOLDER…); the rest live in docs/ so the top of the folder stays short.
# Both places are checked, so nothing gets to be undocumentable by moving it.
DOCS = sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").glob("*.md"))
# "no subscriptions" is the promise; "subscription required" is the bug. Only
# phrases that assert something is sold are flagged.
MONEY_WORDS = ("free trial", "per month", "paid plan", "upgrade to",
               "credit card required", "subscription required", "billed")
# Generated files are produced BY the code, so holding them to a literal count is
# circular: a run of tools/crosscheck.py rewrites CROSSCHECK.md including its own
# "docs agree with the code" row. The generators have their own freshness checks
# (`gen_tools_doc.py --check`, and crosscheck re-runs itself), so they are exempt here.
GENERATED = {"CROSSCHECK.md", "TOOLS.md"}

# Files that exist only after something has run. Holding the docs to their existence would
# mean committing a stale copy of a file that is meant to be fresh.
RUNTIME_FILES = {"check-report.txt"}

PATH_RE = re.compile(r"`([A-Za-z0-9_./\\-]+\.(?:py|md|bat|iss|spec|vbs|txt|json|html))`")


def main() -> int:
    ok = True
    n_tools = len(tools.TOOLS)
    n_engines = len(cost.LOCAL_PROVIDERS) - 1          # minus "lite"

    # ---------- 1. counts in the docs match the code -------------------
    bad_counts = []
    for doc in [d for d in DOCS if d.name not in GENERATED]:
        text = doc.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)   # quoted output, not claims
        for m in re.finditer(r"\b(\d+) tools\b", text):
            line = text[text.rfind("\n", 0, m.start()) + 1: text.find("\n", m.end())]
            # "65 MCP tools" and "91 tools total" are different measurements and
            # legitimately differ from the built-in count.
            if "mcp" in line.lower() or "total" in line.lower():
                continue
            if int(m.group(1)) != n_tools:
                bad_counts.append(f"{doc.name}: says {m.group(1)} tools, code has {n_tools}")
        for m in re.finditer(r"\b(\d+) local engines\b", text):
            if int(m.group(1)) != n_engines:
                bad_counts.append(f"{doc.name}: says {m.group(1)} local engines, "
                                  f"code has {n_engines}")
    print(f"1) counts match code   : {len(DOCS)} docs, {n_tools} tools, "
          f"{n_engines} engines, {len(bad_counts)} mismatch  "
          f"{'OK' if not bad_counts else 'FAIL'}")
    for line in bad_counts:
        print("   ", line)
    ok &= not bad_counts

    # ---------- 2. every file a doc points at exists -------------------
    missing = []
    SKIP = {"settings.json", "weather_cache.json", "ArcDesk.exe", "ArcDeskVoice.exe",
            "profile.json", "nudges.json", "voices.json",
            "ArcDeskSetup.exe", "requirements.txt",
            # written BY the diagnostic, at the user's machine, not shipped here
            "ArcDeskDiag.txt",
            # written when the person double-clicks the launcher / the diagnosis route
            "jarvis-start-log.txt", "jarvis-diagnose-log.txt",
            "jarvis-update-log.txt",
            # created INSIDE fix packs by tools/make_fixpack.py, never in the project
            "FIXPACK.txt",
            # written by the running app (instance.port_file()) into its data folder
            "lockport.txt",
            # written by the running app (logs.crash_bundle()) into its data folder
            "crash-report.txt"}
    # One index of every file in the tree. A doc that writes "build_all.bat" is telling
    # the truth when the file is at packaging/build_all.bat — the old version only
    # resolved bare names against *.py, so an honest sentence got reported as a lie.
    _SKIP_DIRS = {".git", "dist", "node_modules", "__pycache__", "packaging/work",
                  ".venv", ".pytest_cache"}
    tree_names = set()
    for p_ in ROOT.rglob("*"):
        rel_parts = p_.relative_to(ROOT).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        if p_.is_file():
            tree_names.add(p_.name)

    for doc in DOCS:
        for token in PATH_RE.findall(doc.read_text(encoding="utf-8")):
            rel = token.replace("\\", "/").strip()
            if rel in SKIP or rel.startswith(("%", "~")) or Path(rel).name in RUNTIME_FILES:
                continue
            if (ROOT / rel).exists():
                continue
            # docs also refer to files by bare name ("config.py", "build_all.bat") —
            # resolve those against the whole tree before calling them missing
            if Path(rel).name in tree_names:
                continue
            missing.append(f"{doc.name} → {token}")
    print(f"2) referenced files    : {len(missing)} missing  "
          f"{'OK' if not missing else 'FAIL'}")
    for line in missing:
        print("   ", line)
    ok &= not missing

    # ---------- 3. no money language crept back -----------------------
    money = []
    for doc in DOCS:
        low = doc.read_text(encoding="utf-8").lower()
        for word in MONEY_WORDS:
            if word in low:
                money.append(f"{doc.name}: {word!r}")
    print(f"3) no money language   : {len(money)} hits  {'OK' if not money else 'FAIL'}")
    for line in money:
        print("   ", line)
    ok &= not money

    # ---------- 4. the docs that must exist ---------------------------
    required = ["README.md", "INSTALL.md", "FREE.md", "GITHUB.md", "MAGIC.md",
                "WAKE.md", "SHADOW.md", "PERFORMANCE.md", "OPEN_SOURCE.md",
                "CREDITS.md", "ROADMAP.md", "VISION.md", "BOOT.md"]
    absent = [r for r in required if not (ROOT / r).exists()]
    print(f"4) required docs       : {len(required)} expected, {len(absent)} absent  "
          f"{'OK' if not absent else 'FAIL'}")
    ok &= not absent

    # ---------- 5. every test file is referenced somewhere ------------
    tests = {p.name for p in (ROOT / "tests").glob("test_*.py")}
    blob = "\n".join(d.read_text(encoding="utf-8") for d in DOCS)
    unreferenced = sorted(t for t in tests if t not in blob)
    print(f"5) tests documented    : {len(tests)} tests, {len(unreferenced)} unmentioned  "
          f"{'OK (informational)' if not unreferenced else 'note'}")
    if unreferenced:
        print("    not in any doc:", ", ".join(unreferenced))

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
