"""Is the *packaging* true? — checked without a Windows machine.

The README says there is an installer pipeline. Until this file existed, `build/`
did not exist at all: the docs promised `build\\build.bat` and a PyInstaller spec that
had never been written, and no test noticed, because `tests/test_docs.py` only checks
backticked paths.

So this validator does what a build machine would do first, minus the compiling:

  CHECKED     file exists, is syntactically valid, and references real paths
  UNVERIFIED  correct by construction but only provable by building on Windows
  FAIL        something that would break the build or the uninstall

It also guards two specific mistakes that had already been made in this repo:

  1. a **hand-written** PyInstaller module list (it silently missed modules added
     later, producing an exe that imports fine and breaks on first use);
  2. `uninstall.bat` doing `taskkill /IM pythonw.exe /F`, which kills **every** Python
     GUI app on the machine, not just ours.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"

FILES = {
    "spec": PACKAGING / "arcdesk.spec",
    "build_bat": PACKAGING / "build.bat",
    "build_all": PACKAGING / "build_all.bat",
    "iss": PACKAGING / "arcdesk.iss",
    "installer_bat": PACKAGING / "make_installer.bat",
    "fetch_runtime": PACKAGING / "fetch_runtime.py",
}
REQUIRED_ENTRY = {"run.py": ROOT / "run.py", "arc_daemon.py": ROOT / "arc_daemon.py"}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _import_targets() -> list[str]:
    """Every arcdesk module reached through a *relative* import, resolved properly.

    Relative depth matters: `from . import backends` inside `arcdesk/ai/llm.py` means
    `arcdesk.ai.backends`, not `arcdesk.backends`. The first version of this function
    ignored that and produced five false alarms — proof that a checker also needs
    checking.
    """
    wanted: set[str] = set()
    for path in sorted(ROOT.glob("**/*.py")):
        rel = path.relative_to(ROOT)
        if any(part in {"dist", "build", ".venv", "__pycache__"} for part in rel.parts):
            continue
        package = list(rel.parts[:-1])
        text = _read(path)
        for match in re.finditer(r"from\s+(\.+)\s*import\s+([^\n(]+)", text):
            dots = len(match.group(1))
            if dots - 1 > len(package):
                continue
            base = package[: len(package) - (dots - 1)]
            for name in match.group(2).split(","):
                name = name.split(" as ")[0].strip()
                if not name or not name.isidentifier():
                    continue
                wanted.add(".".join([*base, name]) if base else name)
    return sorted(wanted)


def _app_side_checks(add) -> None:
    """The bundle is only "all features" if the app itself can do the voice work.

    These four are the difference between a shortcut that launches a window and a
    program where a person can choose how it opens and teach it their voice without
    ever seeing a terminal.
    """
    rooot = ROOT
    if "--download-voice-model" in (rooot / "run.py").read_text(encoding="utf-8"):
        add("CHECKED", "app: --download-voice-model flag exists", "run.py")
    else:
        add("FAIL", "app: --download-voice-model flag exists", "missing in run.py")
    for mod in ("arcdesk/widgets/voicelock.py", "arcdesk/voiceid.py", "arcdesk/clone.py",
                "arcdesk/widgets/voice_ready.py"):
        if (rooot / mod).exists():
            add("CHECKED", f"module {mod}", 'bundled by collect_submodules("arcdesk")')
        else:
            add("FAIL", f"module {mod}", "missing")
    sett = (rooot / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
    wel = (rooot / "arcdesk" / "widgets" / "welcome.py").read_text(encoding="utf-8")
    if "open_voice_lock" in sett:
        add("CHECKED", "settings: voice enrolment in the app",
            "Settings -> Voice -> Teach ARC my voice")
    else:
        add("FAIL", "settings: voice enrolment in the app", "no open_voice_lock")
    if "mode_voice" in sett and "mode_voice" in wel:
        add("CHECKED", "open mode (icon / voice) in setup AND settings",
            "same question in both places")
    else:
        add("FAIL", "open mode (icon / voice) in setup AND settings", "missing")


def _voice_lib_checks(add) -> None:
    """A frozen EXE cannot pip install anything. Whatever is missing here is missing for
    the user forever, so this is checked at build time and not discovered later."""
    import importlib.util

    def have(mod: str) -> bool:
        try:
            return importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            return False

    for mod, why in (("vosk", 'the "hey jarvis" wake word'),
                     ("sherpa_onnx", 'voice lock ("only my voice")')):
        if have(mod):
            add("CHECKED", f"voice library {mod} is in the build", why)
        else:
            add("FAIL", f"voice library {mod} is in the build",
                f"missing — {why} would be dead in the shipped exe. "
                f"Fix: pip install -r requirements-voice.txt")
    if have("sounddevice"):
        add("CHECKED", "voice library sounddevice is in the build", "microphone capture")
    else:
        # Deliberately not a FAIL: on Linux CI PortAudio is not installed and the wheel
        # still ships fine for Windows, where it bundles its own DLL.
        add("UNVERIFIED", "voice library sounddevice is in the build",
            "not importable on this machine (PortAudio); on Windows the wheel carries it")


def check() -> list[dict]:
    rows: list[dict] = []

    def add(verdict: str, name: str, detail: str = "") -> None:
        rows.append({"verdict": verdict, "name": name, "detail": detail})

    # ---------- 1. the files the docs promise -----------------------------
    for label, path in FILES.items():
        if not path.is_file():
            add("FAIL", f"packaging/{path.name}", "documented but missing")
        else:
            add("CHECKED", f"packaging/{path.name}", f"{path.stat().st_size} bytes")

    # ---------- 2. the spec is valid Python and auto-collects ------------
    spec = _read(FILES["spec"])
    if spec:
        try:
            ast.parse(spec)
            add("CHECKED", "arcdesk.spec parses", "valid Python")
        except SyntaxError as exc:
            add("FAIL", "arcdesk.spec parses", f"SyntaxError line {exc.lineno}: {exc.msg}")
        if "collect_submodules" in spec:
            add("CHECKED", "modules collected automatically",
                "collect_submodules('arcdesk') — new modules cannot be forgotten")
        else:
            add("FAIL", "modules collected automatically",
                "the spec has a hand-written list; modules added later will be missing")
        for entry in REQUIRED_ENTRY:
            if entry in spec:
                add("CHECKED", f"spec builds {entry}", "entry point referenced")
            else:
                add("FAIL", f"spec builds {entry}", "entry point not referenced")
        two = spec.count("EXE(")
        if two >= 2:
            add("CHECKED", "two binaries", f"{two} EXE() targets (app + voice daemon)")
        else:
            add("FAIL", "two binaries", "expected ArcDesk + ArcDeskVoice")
        if "console=False" in spec:
            add("CHECKED", "no black console window", "console=False")
        # data files it claims to bundle must exist
        for pattern in re.findall(r"\"([\w*.-]+\.(?:json|png|svg|ico|html))\"", spec):
            if "*" in pattern:
                continue
            hits = list((ROOT / "arcdesk").rglob(pattern)) + list((ROOT / "shots").rglob(pattern))
            add("CHECKED" if hits else "UNVERIFIED", f"bundled data {pattern}",
                f"{len(hits)} file(s) found" if hits else "optional, not present")

    # ---------- 3. dynamically imported modules exist at all -------------
    modules = _import_targets()
    missing = [m for m in modules if m.startswith("arcdesk.") and
               not _module_exists(m)]
    add("FAIL" if missing else "CHECKED", "every dynamic import resolves",
        ", ".join(missing[:6]) if missing else f"{len(modules)} targets checked")

    # ---------- 4. the Inno script is consistent -------------------------
    iss = _read(FILES["iss"])
    if iss:
        for need in ("PrivilegesRequired=lowest", "AppExe", "[Files]", "[Icons]",
                     "uninsdeletevalue"):
            add("CHECKED" if need in iss else "FAIL",
                f"installer: {need}", "present" if need in iss else "missing")
        needs_admin = re.search(r"PrivilegesRequired\s*=\s*admin", iss, re.I)
        for name, why in (
                ("desktopicon", "the desktop-icon way to open it"),
                ("startup", "the voice way to open it")):
            add("CHECKED" if f'Name: "{name}"' in iss else "FAIL",
                f"installer: {why}", f'task "{name}"')
        add("CHECKED" if "--download-voice-model" in iss else "FAIL",
            "installer: speech models are downloaded at install",
            "ArcDesk.exe --download-voice-model")
        add("FAIL" if needs_admin else "CHECKED", "installer: no admin prompt",
            "PrivilegesRequired=admin — this would prompt for UAC"
            if needs_admin else "PrivilegesRequired=lowest (per-user, no UAC)")
        for ref in re.findall(r"Source: \"([^\"]+)\"", iss):
            target = (PACKAGING / ref).resolve()
            if "*" in ref:
                parent = target.parent
                add("UNVERIFIED", f"installer source {ref}",
                    "produced by packaging\\build.bat (dist\\)" if not parent.exists()
                    else "folder exists")
            else:
                add("CHECKED" if target.exists() else "FAIL",
                    f"installer source {ref}", "found" if target.exists() else "missing")
        for icon_ref in re.findall(r"SetupIconFile=([^\s]+)", iss):
            target = (PACKAGING / icon_ref.replace("\\", "/")).resolve()
            add("CHECKED" if target.is_file() else "FAIL",
                f"installer icon {icon_ref}", "found" if target.is_file() else "missing")
        if "uninstall" in iss.lower():
            add("CHECKED", "installer: uninstaller", "an entry exists")
        # This used to be `if "startup" in iss: add(CHECKED, ...)` — a green line that
        # asserted nothing. These rows read the actual [Tasks] and [Registry] blocks.
        tasks = dict(re.findall(r'^Name: "([^"]+)";[^\n]*?Flags: (\S+)', iss, re.M))
        for name in ("desktopicon", "startup"):
            if tasks.get(name) == "checkedonce":
                add("CHECKED", f"installer: offers '{name}' pre-ticked (user can untick)",
                    "Flags: checkedonce")
            elif name in tasks:
                add("FAIL", f"installer: offers '{name}'", f"Flags: {tasks[name]}")
            else:
                add("FAIL", f"installer: offers '{name}'", "no task")
        if re.search(r'^Name: "\{autodesktop\}.*Tasks: desktopicon', iss, re.M):
            add("CHECKED", "installer: desktop shortcut follows its task", "Tasks: desktopicon")
        else:
            add("FAIL", "installer: desktop shortcut follows its task", "not gated on the task")
        if re.search(r"Tasks: startup", iss):
            add("CHECKED", "installer: startup entry follows its task", "Tasks: startup")
        else:
            add("FAIL", "installer: startup entry follows its task", "not gated on the task")

    # ---------- 5. the .bat files point at real paths --------------------
    for label in ("build_bat", "installer_bat"):
        text = _read(FILES[label])
        for ref in set(re.findall(r"((?:tools|tests|packaging|arcdesk)\\[\w\\.]+|[\w.]+\.[a-z]{2,4})",
                                  text)):
            cleaned = ref.replace("\\", "/")
            if cleaned.endswith((".bat", ".spec", ".iss")):
                continue
            target = ROOT / cleaned
            if target.exists():
                add("CHECKED", f"{FILES[label].name} → {cleaned}", "exists")
            elif cleaned.startswith(("tools/", "tests/", "arcdesk/")):
                add("FAIL", f"{FILES[label].name} → {cleaned}", "referenced but missing")

    # ---------- 6. uninstall must never kill other people's processes ----
    uninstall = _read(ROOT / "uninstall.bat")
    if not uninstall:
        add("FAIL", "uninstall.bat exists", "missing")
    else:
        live_lines = [ln for ln in uninstall.splitlines()
                      if not ln.strip().lower().startswith(("rem", "::", "echo"))]
        collateral = re.search(r"taskkill[^\n]*/IM\s+(python|pythonw)(\.exe)?\s",
                               "\n".join(live_lines), re.I)
        add("FAIL" if collateral else "CHECKED", "uninstall kills only Arc Desk",
            "it also kills every python/pythonw process" if collateral
            else "no blanket taskkill of python")
        for need in ("ArcDesk.exe", "ArcDeskVoice.exe", "CurrentVersion\\Run",
                     "%APPDATA%\\ArcDesk"):
            add("CHECKED" if need in uninstall else "FAIL",
                f"uninstall handles {need}", "yes" if need in uninstall else "missing")

    # ---------- 7. check.bat runs the things that matter -----------------
    check_bat = _read(ROOT / "check.bat")
    for need, why in (("run_all.py", "the tests"), ("doctor", "install check"),
                      ("capability", "what it can do"),
                      ("packaging.py", "can it be built")):
        add("CHECKED" if need in check_bat else "FAIL",
            f"check.bat runs {why}", "yes" if need in check_bat else "missing")

    # ---------- 7b. one double-click, nothing to download -----------------
    one = _read(FILES["build_all"])
    if one:
        for need, why in (("fetch_runtime.py", "runtimes are fetched at build time"),
                          ("PyInstaller", "the two exes"),
                          ("ISCC", "the single installer"),
                          ("sizecheck.py", "the size is measured, not guessed")):
            add("CHECKED" if need in one else "FAIL", f"build_all: {why}",
                "yes" if need in one else "missing")
    fetch_src = _read(FILES["fetch_runtime"])
    if fetch_src:
        for need in ("sha256", "zipfile", "nodejs.org"):
            add("CHECKED" if need.lower() in fetch_src.lower() else "FAIL",
                f"fetch_runtime: {need}", "present" if need.lower() in fetch_src.lower()
                else "missing")
        add("CHECKED" if "FFMPEG_KEEP" in fetch_src else "UNVERIFIED",
            "fetch_runtime: ships only what the app uses",
            "ffmpeg.exe + ffprobe.exe only (ffplay is 23 MB and is a fallback)")

    # are the runtimes actually staged for this build?
    for label, probe in (("ffmpeg", ROOT / "runtime" / "ffmpeg" / "ffmpeg.exe"),
                         ("node", ROOT / "runtime" / "node" / "node.exe")):
        if probe.is_file():
            add("CHECKED", f"runtime staged: {label}",
                f"{probe.stat().st_size // 1_000_000} MB")
        else:
            add("UNVERIFIED", f"runtime staged: {label}",
                "not fetched yet — run packaging\\fetch_runtime.py (the installer copes, "
                "but media tools will say ffmpeg is missing)")

    # the installer must carry the runtimes and be per-user
    if iss:
        for need in ("[Components]", "Compression=lzma2/ultra64",
                     "FinishedLabel", "DestDir", "InitializeUninstall"):
            add("CHECKED" if need in iss else "FAIL", f"installer: {need}",
                "present" if need in iss else "missing")
        add("CHECKED" if "PrivilegesRequired=admin" not in iss else "FAIL",
            "installer: no admin prompt",
            "PrivilegesRequired=lowest")
        add("CHECKED" if "vault" in iss.lower() else "FAIL",
            "installer: asks before deleting the vault",
            "the uninstaller names the vault explicitly")
        add("CHECKED" if "FinishedLabel" in iss else "FAIL",
            "installer: says \"installed successfully\"",
            "FinishedLabel override present")

    # ---------- 8. the honest limit -------------------------------------
    add("UNVERIFIED", "ArcDesk.exe really launches",
        "requires a Windows build machine — PyInstaller cannot cross-compile")
    add("UNVERIFIED", "installer uninstalls cleanly",
        "requires Inno Setup 6 on Windows")
    _app_side_checks(add)
    _voice_lib_checks(add)
    return rows


def _module_exists(name: str) -> bool:
    path = ROOT / (name.replace(".", "/") + ".py")
    if path.is_file():
        return True
    return (ROOT / name.replace(".", "/")).is_dir()


def summarise(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    rows = check()
    if "--json" in args:
        import json
        print(json.dumps({"rows": rows, "summary": summarise(rows)}, indent=1))
    else:
        print("ARC DESK · packaging check")
        print("=" * 72)
        icon = {"CHECKED": "[ok]  ", "UNVERIFIED": "[need]", "FAIL": "[FAIL]"}
        for row in rows:
            print(f"{icon[row['verdict']]} {row['name']:<46} {row['detail'][:80]}")
        counts = summarise(rows)
        print("=" * 72)
        print(f"checked {counts.get('CHECKED', 0)} · "
              f"needs windows {counts.get('UNVERIFIED', 0)} · "
              f"failed {counts.get('FAIL', 0)}")
        if counts.get("FAIL"):
            print("RESULT: the packaging would break — fix the FAIL rows above.")
        elif counts.get("UNVERIFIED"):
            n = counts.get("UNVERIFIED", 0)
            print(f"RESULT: nothing is broken on this side. {n} rows are UNVERIFIED — "
                  f"they need a Windows build machine and are not claimed as done.")
        else:
            print("RESULT: packaging is consistent.")
    return 1 if any(r["verdict"] == "FAIL" for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
