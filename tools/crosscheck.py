#!/usr/bin/env python3
"""Cross-check everything that was designed — one command, one table.

    python tools/crosscheck.py              # ~90 s, runs the tests and the real app
    python tools/crosscheck.py --quick      # ~5 s, no app boots, no test suite
    python tools/crosscheck.py --json       # machine-readable
    python tools/crosscheck.py --write      # also refresh CROSSCHECK.md (a saved copy)

The claim this file exists to answer, in the user's words: *"intha application nala, ena ena
things irukanum nu design panamo athellam irukanum, work aaganum — cross check paniko"*.

So it does three separate things, and refuses to blur them:

  EXISTS      the file / tool / page is there (counted from the registry, not remembered)
  WORKS       a real check ran and passed — a unit test, or the app actually booting
  UNVERIFIED  physically impossible to prove in this sandbox (no microphone, no Windows,
              no display) — printed, never silently promoted to "works"

Every row names the command or test behind it. If a row says WORKS, something executed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# --------------------------------------------------------------------------------------
# What was designed, and what proves it. The right-hand side is a test file name or a
# command; a feature with no proof is listed as UNVERIFIED on purpose.
# --------------------------------------------------------------------------------------
FEATURES: list[tuple[str, str, str]] = [
    # (what the user asked for, proof, note)
    ("Application opens by voice", "test_wake_pipeline", "phrase matching, any phrase you set"),
    ("'Bye JARVIS' CLOSES the app", "test_voice_close",
     "real app + real protocol: process exits 0 (tools/voice_roundtrip.py)"),
    ("'Bye JARVIS' three choices (exit/quit/hide)", "test_voice_close",
     "and it never quits into silence"),
    ("Magic mode (fullscreen ARC + wallpaper, restored on exit)", "test_magic",
     "journal + crash-safe restore"),
    ("Windows untouched (no shell/taskbar/explorer changes)", "test_magic",
     "tools/desktop_check.py --scan is the source scan"),
    ("Gravity charms (floating sprites, click-through)", "test_magic", "painted, not images"),
    ("Holographic deck", "test_holo", "CPU rasteriser, 30 fps budget"),
    ("86 tools, every one answers", "test_actions", "tools/capability.py executes them"),
    ("ARC Lite offline brain", "test_lite_intents", "~1 ms, no model"),
    ("Real local LLM over HTTP", "test_agent_loop", "engine as backend, localhost only"),
    ("Streaming + barge-in", "test_stream", ""),
    ("Voice: OS TTS, manly neural voice, language mirroring", "test_voice", ""),
    ("Machine-acting layer (windows, keys, clicking, OCR)", "test_uia", "UIA + OCR"),
    ("Reading any file (pdf/docx/xlsx/pptx/csv/image/audio)", "test_reading", ""),
    ("Editing files without overwriting the original", "test_reading", "new sibling file"),
    ("Media studio: video, audio, image", "test_media", "ffmpeg/Pillow, free"),
    ("Playback of your own music/video, external disks", "test_playback", ""),
    ("search_inside: the words inside your documents", "test_inside", ""),
    ("pc_health: 'why is this PC slow'", "test_pchealth", "two measured samples"),
    ("explain: read an error and quote it first", "test_catalog", "24 error families"),
    ("Backup with SHA-256 proof", "test_backup", ""),
    ("Autostart: one HKCU entry, read back", "test_backup", ""),
    ("First-run wizard (five decisions)", "test_firstrun", ""),
    ("Coach / mentor / analyst modes", "test_coach", ""),
    ("Medicine rails + crisis numbers", "test_health", "information, never a prescription"),
    ("Markets: quotes, arithmetic, position size", "test_market", ""),
    ("Business, travel, craft, data mining", "test_business", ""),
    ("Reminders, focus sessions, briefing", "test_reminders", ""),
    ("Learned voice macros", "test_macros", ""),
    ("MCP tool servers", "test_mcp", "7 reference servers"),
    ("86-package free/open-source catalogue", "test_packages", ""),
    ("Money: free enforced in code", "test_free_guard", "no paid path"),
    ("Docs match the code (counts, files, tests)", "test_docs", "test_docs.py rule 1 + 2"),
    ("Packaging: spec, installer, uninstaller", "test_packaging", "tools/packaging.py"),
    ("The real entry point boots", "test_firstrun", "tools/smoke_firstrun.py"),
    ("Asks icon-vs-voice at setup, and again in Settings", "test_openmode",
     "one answer -> two flags; downgrades honestly"),
    ("Command voices AND reply voices, kept apart", "test_voicelib",
     "any voice may be allowed; any clip may be the reply voice"),
    ("Voice enrolment inside the app", "test_voicelock_gui",
     "3 takes, level bar, WAV fallback, lock switch"),
    ("Every Settings control actually changes something", "test_audit",
     "reads the AST: no dead switches, no unread defaults"),
    ("All 88 tools are callable, described, schema-valid", "test_audit",
     "and listed in TOOLS.md + the in-app page"),
    ("Moves to another laptop without carrying its voice lock", "test_move",
     "pack/unpack, keys stripped, voiceid excluded, merge keeps both"),
    ("Three languages, and clips graded before cloning", "test_clean",
     "ta/hi -> IndicF5, en -> XTTS, SNR before/after"),
    ("Speaks in the imported voice, per language", "test_clone",
     "IndicF5 for Tamil/Indic, XTTS for English, piper/SAPI fallback"),
    ("Only the enrolled voice may command it", "test_voiceid",
     "per-machine profiles, threshold from self-similarity"),
    ("Real photographs, with credit (not a drawing)", "test_photo",
     "Wikimedia Commons, free licences, no key, no GPU"),
    ("The Vault: projects, notes, progress, export", "test_vault",
     "copy-not-move, verified export, 0.45 ms saves"),
    ("One-click installer (payload + script)", "test_packaging",
     "packaging/build_all.bat + fetch_runtime.py + arcdesk.iss"),
]

UNVERIFIABLE = [
    ("ArcDesk.exe launches after PyInstaller", "needs a Windows build machine"),
    ("Vosk hears your actual voice", "needs a microphone + the speech model"),
    ("Windows 11 UI behaves as documented", "needs a Windows desktop"),
    ("Inno Setup produces Setup.exe", "needs Inno Setup 6 on Windows"),
]

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:30]!r}")
    ok &= bool(good)


def run(cmd: list[str], timeout: int = 300, env_extra: dict | None = None):
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.update(env_extra or {})
    try:
        return subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True,
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timeout")


def main(argv: list[str]) -> int:
    quick = "--quick" in argv
    as_json = "--json" in argv
    write_md = "--write" in argv
    report: dict = {"exists": [], "works": [], "unverified": [], "failed": []}

    def row(state: str, label: str, detail: str = "") -> None:
        report[state].append({"what": label, "detail": detail})
        if not as_json:
            icon = {"exists": "[ok]  ", "works": "[ok]  ", "failed": "[FAIL]",
                    "unverified": "[need]"}[state]
            print(f"{icon} {label:<58} {detail[:70]}")

    if not as_json:
        print("ARC DESK · cross-check")
        print("=" * 92)
        print("1. IS EVERYTHING THAT WAS DESIGNED ACTUALLY HERE?")

    # ---------------------------------------------------------------- 1. exists
    from arcdesk.ai import tools as toolreg
    row("exists", f"{len(toolreg.TOOLS)} tools in the registry",
        f"{sum(1 for t in toolreg.TOOLS.values() if t.confirm)} ask before acting")
    docs = sorted(p.name for p in ROOT.glob("*.md"))
    row("exists", f"{len(docs)} documents", ", ".join(docs[:4]) + " …")
    tests = sorted(p.stem for p in (ROOT / "tests").glob("test_*.py"))
    row("exists", f"{len(tests)} test files", "")
    for name in ("arcdesk/TOOLS_PAGE.html", "arcdesk/KNOWS_PAGE.html",
                 "packaging/arcdesk.spec", "packaging/build.bat", "packaging/arcdesk.iss",
                 "packaging/make_installer.bat", "packaging/build_all.bat",
                 "arcdesk/photo.py", "arcdesk/clone.py", "arcdesk/voiceid.py",
                 "arcdesk/widgets/voicelock.py",
                 "tools/voice_setup.py", "tools/clean_voice.py", "tools/move.py",
                 "install_clone.bat", "MOVE.md",
                 "VOICE.md",
                 "packaging/fetch_runtime.py", "assets/arc_icon.ico", "TOOLS.md",
                 "uninstall.bat", "check.bat", "install.bat", "install_voice.bat"):
        # long-form docs live in docs/ since fix48; either place counts as "exists"
        here = (ROOT / name).is_file() or (ROOT / "docs" / Path(name).name).is_file()
        row("exists" if here else "failed", name, "")
    missing_pages = [p for p in ("TOOLS_PAGE.html", "KNOWS_PAGE.html")
                     if not (ROOT / "arcdesk" / p).is_file()]
    if missing_pages:
        row("failed", "generated pages", ", ".join(missing_pages))

    # ---------------------------------------------------------------- 2. freshness
    if not as_json:
        print("\n2. IS THE WRITTEN WORD STILL TRUE?")
    gen = run([sys.executable, "tools/gen_tools_doc.py", "--check"], timeout=120)
    row("works" if gen.returncode == 0 else "failed", "TOOLS.md + TOOLS_PAGE.html current",
        (gen.stdout or gen.stderr).strip().splitlines()[0][:70] if gen.stdout else "")
    pack = run([sys.executable, "tools/packaging.py", "--json"], timeout=120)
    try:
        pack_rows = json.loads(pack.stdout or "{}").get("rows", [])
    except json.JSONDecodeError:
        pack_rows = []
    pack_fail = [r for r in pack_rows if r["verdict"] == "FAIL"]
    row("works" if not pack_fail else "failed", "packaging consistent",
        f"{len(pack_rows)} checks, {len(pack_fail)} failed")
    doc = run([sys.executable, "tests/test_docs.py"], timeout=180)
    row("works" if doc.returncode == 0 else "failed", "docs agree with the code",
        "counts, files, tests" if doc.returncode == 0 else (doc.stdout or "")[-90:])

    # ---------------------------------------------------------------- 3. works
    if not as_json:
        print("\n3. DOES IT ACTUALLY WORK?  (each row is a command that ran)")
    passed: set[str] = set()
    failed_tests: list[str] = []
    if quick:
        row("unverified", "the test suite", "--quick: not run")
    else:
        suite = run([sys.executable, "tests/run_all.py"], timeout=1200)
        for line in (suite.stdout or "").splitlines():
            m = re.match(r"(PASS|FAIL)\s+(\S+)", line.strip())
            if m:
                (passed.add if m.group(1) == "PASS" else failed_tests.append)(m.group(2))
        total = len(passed) + len(failed_tests)
        row("works" if not failed_tests else "failed",
            f"{len(passed)}/{total} tests pass",
            ", ".join(failed_tests[:4]) if failed_tests else "the whole suite")

    # voice round-trip: the promise the user keeps repeating
    if quick:
        row("unverified", "open/close by voice (end-to-end)", "--quick: not run")
    else:
        vr = run([sys.executable, "tools/voice_roundtrip.py", "--case", "quit"], timeout=300)
        row("works" if vr.returncode == 0 else "failed",
            "BYE JARVIS closes the application", "real app, real protocol, exit 0"
            if vr.returncode == 0 else (vr.stdout or "")[-90:])
        boot = run([sys.executable, "tools/smoke_firstrun.py", "--shadow", "--no-instance",
                    "--seconds", "5"], timeout=300)
        row("works" if boot.returncode == 0 else "failed", "the app boots (run.py --shadow)",
            "settings written, clean exit" if boot.returncode == 0 else (boot.stdout or "")[-90:])
        spd = run([sys.executable, "tools/speedcheck.py", "--json"], timeout=300)
        try:
            sp = json.loads(spd.stdout or "{}")
            row("works" if spd.returncode == 0 else "failed", "Answer speed measured",
                f"Lite p50 {sp.get('lite', {}).get('p50', '?')} ms · routing "
                f"{sp.get('routing', {}).get('p50', '?')} ms")
        except json.JSONDecodeError:
            row("failed", "Answer speed measured", "speedcheck produced no JSON")
        cap = run([sys.executable, "tools/capability.py", "--all"], timeout=600)
        last = [ln for ln in (cap.stdout or "").splitlines() if "live" in ln]
        row("works" if cap.returncode == 0 else "failed", "every tool answers when called",
            last[-1] if last else (cap.stdout or "")[-70:])

    # ---------------------------------------------------------------- 4. features
    if not as_json:
        print("\n4. FEATURE BY FEATURE — a passing test is the proof")
    for label, proof, note in FEATURES:
        if proof not in tests:
            row("failed", label, f"no test file named {proof}.py")
        elif quick:
            row("unverified", label, f"{proof}.py exists (suite not run)")
        elif proof in passed:
            row("works", label, note or f"{proof}.py")
        else:
            row("failed", label, f"{proof}.py did not pass")

    # ---------------------------------------------------------------- 5. honest
    if not as_json:
        print("\n5. WHAT THIS MACHINE CANNOT PROVE (never counted as done)")
    for label, why in UNVERIFIABLE:
        row("unverified", label, why)

    # ---------------------------------------------------------------- saved copy
    if write_md:
        import datetime
        lines = [
            "# ARC DESK — cross-check (generated)",
            "",
            f"Last run: {datetime.datetime.now().strftime('%d %B %Y, %H:%M')} · "
            f"`python tools/crosscheck.py --write`",
            "",
            "Every `ok` below is a command that ran. `need` means this machine physically "
            "cannot prove it (no Windows build machine, no microphone, no desktop).",
            "",
            "| | what | how it was checked |",
            "|---|---|---|",
        ]
        for state, label in (("exists", "present"), ("works", "PROVEN"),
                             ("failed", "FAILED"), ("unverified", "cannot prove here")):
            for r in report[state]:
                mark = {"exists": "ok", "works": "**ok**", "failed": "**FAIL**",
                        "unverified": "need"}[state]
                lines.append(f"| {mark} | {r['what']} | {r['detail'] or label} |")
        c = {k: len(v) for k, v in report.items()}
        lines += ["", f"**{c['exists']} present · {c['works']} proven · "
                      f"{c['failed']} failed · {c['unverified']} cannot prove here.**", ""]
        (ROOT / "CROSSCHECK.md").write_text("\n".join(lines), encoding="utf-8")
        if not as_json:
            print("\nwrote CROSSCHECK.md")

    # ---------------------------------------------------------------- summary
    counts = {k: len(v) for k, v in report.items()}
    if as_json:
        report["summary"] = counts
        print(json.dumps(report, indent=1))
    else:
        print("\n" + "=" * 92)
        print(f"here {counts['exists']} · proven {counts['works']} · "
              f"failed {counts['failed']} · cannot prove here {counts['unverified']}")
        if counts["failed"]:
            print("RESULT: something is missing or broken — the FAIL rows are above.")
        else:
            print("RESULT: everything that was designed is present, and everything that "
                  "can be executed here passed.")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
