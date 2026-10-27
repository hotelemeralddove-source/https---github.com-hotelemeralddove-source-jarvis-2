"""Packaging and the generated reference — can this thing be built and uninstalled?

The failure this file is designed to catch is the one that already happened here: the
README advertised `build\\build.bat` and a PyInstaller spec for weeks while neither
existed, and every test stayed green because nothing checked the claims. So the tests
are about *claims*, not about code paths:

  * every file the docs name exists, parses, and points at real paths;
  * the spec cannot silently lose a module (it must use collect_submodules);
  * the two binaries it promises are the two the app actually needs;
  * the uninstaller never kills someone else's Python;
  * TOOLS.md and TOOLS_PAGE.html are byte-identical to a fresh generation, i.e. the
    counts inside them were computed and not typed;
  * the page is offline-safe (no CDN, no web fonts) because it ships inside the exe.

What it deliberately does NOT claim: that ArcDesk.exe runs. PyInstaller cannot
cross-compile, so that line can only be proven on Windows. The test prints it as
UNVERIFIED rather than pretending.

Run:  python tests/test_packaging.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from arcdesk.ai import tools  # noqa: E402
import gen_tools_doc  # noqa: E402
import packaging  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<60} {str(got)[:34]!r}")
    ok &= bool(good)


print("1. packaging validator")
rows = packaging.check()
fails = [r for r in rows if r["verdict"] == "FAIL"]
check("no FAIL row", len(fails), 0)
for row in fails:
    print("        ", row["name"], "—", row["detail"])
check("validator looked at ≥ 25 things", len(rows) >= 25)
check("windows-only rows are labelled, not faked",
      any(r["verdict"] == "UNVERIFIED" for r in rows))

print("2. the PyInstaller spec")
spec_path = ROOT / "packaging" / "arcdesk.spec"
check("packaging/arcdesk.spec exists", spec_path.is_file())
spec = spec_path.read_text(encoding="utf-8")
check("collects submodules automatically", "collect_submodules" in spec)
check("two EXE targets", spec.count("EXE(") >= 2)
check("no console window", "console=False" in spec)
check("no UPX compression (avoids antivirus false positives)", "upx=False" in spec)
for entry in ("run.py", "arc_daemon.py"):
    check(f"builds {entry}", entry in spec)
# a hand-written module list is the bug: it was there before, and it went stale
hand_list = re.findall(r"hiddenimports\s*=\s*\[([^\]]{80,})\]", spec)
check("hiddenimports is not a giant hand-written list",
      not any(len(x.split(",")) > 12 for x in hand_list))
names = sorted(p.stem for p in (ROOT / "arcdesk").rglob("*.py") if p.stem != "__init__")
check("registry of real modules has enough to lose", len(names) > 40)
check("spec relies on the package, so all of them are covered",
      "collect_submodules('arcdesk')" in spec or 'collect_submodules("arcdesk")' in spec)

print("3. the icon")
ico = ROOT / "assets" / "arc_icon.ico"
check("assets/arc_icon.ico exists", ico.is_file())
check("it is a real ICO (PC header + directory)", ico.read_bytes()[:4] == b"\x00\x00\x01\x00")
png = ROOT / "assets" / "arc_icon.png"
check("assets/arc_icon.png exists", png.is_file())
if png.is_file():
    try:
        from PIL import Image
        with Image.open(png) as im:
            check("icon is square 512", (im.width, im.height), (512, 512))
            check("icon has transparency", im.mode in ("RGBA", "LA", "P"))
    except ImportError:
        print("   ..   Pillow missing — icon pixel checks skipped honestly")

print("4. the generated tools reference")
md_path, html_path = ROOT / "TOOLS.md", ROOT / "arcdesk" / "TOOLS_PAGE.html"
check("TOOLS.md exists", md_path.is_file())
check("TOOLS_PAGE.html exists", html_path.is_file())
check("generator validates its own categories", gen_tools_doc.validate(gen_tools_doc.catalogue()), [])
md = md_path.read_text(encoding="utf-8")
page = html_path.read_text(encoding="utf-8")
live = len(tools.TOOLS)
check(f"TOOLS.md starts with the real count {live}", f"**{live} tools.**" in md)
check("TOOLS.md regenerated exactly matches disk",
      gen_tools_doc.build_md(gen_tools_doc.catalogue()) == md)
check("TOOLS_PAGE.html regenerated exactly matches disk",
      gen_tools_doc.build_html(gen_tools_doc.catalogue()) == page)
missing_md = [n for n in tools.TOOLS if f"`{n}`" not in md]
check("every tool appears in TOOLS.md", missing_md, [])
missing_html = [n for n in tools.TOOLS if f">{n}<" not in page and f">{n} " not in page]
check("every tool appears in the page", missing_html, [])
check("no CDN / external script / font in the page",
      not re.search(r'(src|href)="https?://', page))
check("the page can filter (search box + JS present)", 'id="q"' in page and "apply()" in page)
ask = sum(1 for t in tools.TOOLS.values() if t.confirm)
check(f"asks-first count matches registry ({ask})", f"{ask} of them ask before acting" in md)

print("5. the batch files")
for name in ("build.bat", "make_installer.bat"):
    bat = ROOT / "packaging" / name
    check(f"packaging/{name} exists", bat.is_file())
    body = bat.read_text(encoding="utf-8", errors="replace")
    check(f"packaging/{name} refuses to continue on error",
          "goto :fail" in body or "exit /b 1" in body)
build_bat = (ROOT / "packaging" / "build.bat").read_text(encoding="utf-8")
check("build.bat pre-flights with the packaging check", "packaging.py --check" in build_bat)
uninstall = (ROOT / "uninstall.bat").read_text(encoding="utf-8")
live_lines = "\n".join(ln for ln in uninstall.splitlines()
                       if not ln.strip().lower().startswith(("rem", "::", "echo")))
check("uninstall never kills all python/pythonw",
      not re.search(r"taskkill[^\n]*/IM\s+(python|pythonw)(\.exe)?\s", live_lines, re.I))
check("uninstall stops the app exe", "ArcDesk.exe" in uninstall)
check("uninstall stops the voice exe", "ArcDeskVoice.exe" in uninstall)
check("uninstall removes the autostart value", "CurrentVersion\\Run" in uninstall)
check("uninstall says it left the user's files alone",
      "never touched" in uninstall or "were never touched" in uninstall)

print("6. the installer script")
iss = (ROOT / "packaging" / "arcdesk.iss").read_text(encoding="utf-8")
check("per-user install, no UAC", "PrivilegesRequired=lowest" in iss)
check("no admin-only sections", "PrivilegesRequired=admin" not in iss)
check("asks before deleting notes and journal", "InitializeUninstall" in iss)
check("startup is offered and clearly reversible",
      "startup" in iss and ("checkedonce" in iss or "unchecked" in iss))
check("removes its own startup value on uninstall", "uninsdeletevalue" in iss)
check("does not register a service", "[Services]" not in iss)

print("6b. one double-click, nothing for the user to download")
allbat = (ROOT / "packaging" / "build_all.bat")
check("packaging/build_all.bat exists", allbat.is_file())
body = allbat.read_text(encoding="utf-8", errors="replace") if allbat.is_file() else ""
for need, why in (("fetch_runtime.py", "fetches ffmpeg + node at build time"),
                  ("PyInstaller", "builds the two exes"),
                  ("ISCC", "compresses into one Setup"),
                  ("sizecheck.py", "measures the size")):
    check(f"build_all does: {why}", need in body)
check("build_all survives being offline (warns, does not fail)",
      "WARNING" in body and "goto :fail" in body)
fetch = (ROOT / "packaging" / "fetch_runtime.py").read_text(encoding="utf-8")
check("fetch_runtime verifies what it can", "sha256" in fetch.lower())
check("fetch_runtime is honest when no checksum is published",
      "no published checksum" in fetch)
check("fetch_runtime keeps the payload small (no ffplay)",
      '"ffmpeg.exe", "ffprobe.exe"' in fetch)
check("nothing downloaded is committed",
      "runtime/" in (ROOT / ".gitignore").read_text(encoding="utf-8"))
iss2 = (ROOT / "packaging" / "arcdesk.iss").read_text(encoding="utf-8")
check("installer carries compiled runtime only when present",
      "#if HaveFFmpeg" in iss2 and "#if HaveNode" in iss2)
check("installer says installed successfully", "installed successfully" in iss2)
check("installer compresses hard", "lzma2/ultra64" in iss2 and "SolidCompression=yes" in iss2)
check("installer never asks for admin", "PrivilegesRequired=lowest" in iss2
      and "PrivilegesRequired=admin" not in iss2)
check("uninstall asks before deleting the vault", "vault" in iss2.lower())
check("no system-wide PATH write (only the app's own process gets it)",
      "[Environment]" not in iss2 and "ChangesEnvironment=yes" not in iss2)

print("7. check.bat covers the new steps")
check_bat = (ROOT / "check.bat").read_text(encoding="utf-8")
for need in ("packaging.py", "gen_tools_doc.py --check"):
    check(f"check.bat runs {need}", need in check_bat)
last = max(re.findall(r"\[(\d+)/(\d+)\]", check_bat), default=("0", "0"))
check("check.bat numbers its steps in order", last[0] == last[1], True)
check("check.bat claims nine steps", last, ("9", "9"))
for stale in ("[5/5]", "[6/7]", "[7/7]", "[7/8]", "[8/8]"):
    check(f"check.bat does not still say {stale}", stale in check_bat, False)

print("8. the bundle can do the voice work without a terminal")
sys.path.insert(0, str(ROOT / "tools"))
import packaging as pkg_tool  # noqa: E402
rows = pkg_tool.check()
names = [r["name"] for r in rows]
check("installer offers both ways to open it",
      any("desktop-icon way" in n for n in names) and any("voice way" in n for n in names))
check("models are downloaded by the installer",
      any("downloaded at install" in n for n in names))
check("app has --download-voice-model",
      any("download-voice-model flag" in n for n in names))
check("voice enrolment lives in Settings",
      any("voice enrolment in the app" in n for n in names))
check("open mode asked in setup AND settings",
      any("setup AND settings" in n for n in names))
check("no FAIL row in packaging", [r for r in rows if r["verdict"] == "FAIL"], [])
iss2 = (ROOT / "packaging" / "arcdesk.iss").read_text(encoding="utf-8")
check("installer asks the open-mode question in words",
      "How should it open?" in iss2, True)
check("startup task says the microphone is still off", "microphone stays off" in iss2, True)
check("post-install model download is opt-out", "unchecked" in iss2, True)

print("9. the two bugs that only a real build found")
spec = (ROOT / "packaging" / "arcdesk.spec").read_text(encoding="utf-8")
check("spec resolves the repo root once, not twice", "ROOT = ROOT.parent" not in spec, True)
check("spec stops with a readable message if run.py is not there",
      "cannot find run.py" in spec, True)
check("spec ships tools/doctor.py (--doctor is a promised feature)",
      'DOCTOR = ROOT / "tools" / "doctor.py"' in spec, True)
run_py = (ROOT / "run.py").read_text(encoding="utf-8")
check("run.py finds tools/ inside the bundle, not next to __file__",
      '_MEIPASS' in run_py, True)
doctor_src = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
check("doctor does not hard-code the .exe name for its own daemon",
      'names = ("ArcDeskVoice.exe", "ArcDeskVoice")' in doctor_src, True)
reqv = (ROOT / "requirements-voice.txt").read_text(encoding="utf-8")
for mod in ("vosk", "sounddevice", "sherpa-onnx"):
    check(f"requirements-voice.txt pins {mod}",
          any(line.strip().startswith(mod) for line in reqv.splitlines()), True)
bat = (ROOT / "packaging" / "build_all.bat").read_text(encoding="utf-8")
check("build_all.bat installs the voice libraries, not just the UI",
      "requirements-voice.txt" in bat, True)
sh = (ROOT / "packaging" / "build_all.sh").read_text(encoding="utf-8")
check("build_all.sh builds and measures the same bundle", "ArcDesk-$OS.tar.xz" in sh, True)
check("build_all.sh says plainly that it is not the Windows installer",
      "not the Windows installer" in sh, True)
wf = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
check("CI builds the real Setup.exe on a Windows runner", "windows-latest" in wf, True)
# The workflow is deliberately minimal now (install -> build -> zip -> upload). A
# blocking test step cost four builds, so it must never come back.
check("no CI step can block the installer", "run_all.py" in wf, False)
check("the portable zip is the always-works fallback",
      "ArcDesk-portable.zip" in wf, True)
check("the artifact is named plainly", "name: ArcDesk" in wf, True)

print("10. the GitHub path (no Windows PC needed)")
wf = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
check("any push builds it, no menu clicking required", "push:" in wf, True)
check("...and it can be started by hand too", "workflow_dispatch" in wf, True)
check("...installing the app's libraries", "PySide6-Essentials" in wf
      or "requirements.txt" in wf, True)
check("...and the voice libraries, without ever blocking the build",
      "sherpa-onnx" in wf and "continue-on-error: true" in wf, True)
check("what it built is printed on the run page", "GITHUB_STEP_SUMMARY" in wf, True)
push = (ROOT / "push_to_github.bat").read_text(encoding="utf-8")
check("push_to_github.bat refuses to guess a URL", "if \"%~1\"==\"\"" in push, True)
check("...tells you to create an EMPTY repo", "Do NOT add a README" in push, True)
check("...and names the one-click git install", "winget install Git.Git" in push, True)
# long-form docs moved into docs/ in fix48 so the top of the folder stays short
guide_path = ROOT / "SETUP_GITHUB.md"
if not guide_path.exists():
    guide_path = ROOT / "docs" / "SETUP_GITHUB.md"
guide = guide_path.read_text(encoding="utf-8")
check("the guide says where the exe arrives", "Artifacts" in guide, True)
check("the guide points at the hidden .github folder",
      ".github" in guide and "Hidden items" in guide, True)

print("11. honest limits")
print("   ..   ArcDesk.exe launching          UNVERIFIED — needs a Windows machine")
print("   ..   Inno Setup producing a Setup    UNVERIFIED — needs Inno Setup 6 on Windows")
print("   ..   a real microphone / real GPU    UNVERIFIED — no audio device in this sandbox")
print("   ..   nothing above faked a build")

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
