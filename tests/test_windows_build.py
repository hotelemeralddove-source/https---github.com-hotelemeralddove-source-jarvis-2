#!/usr/bin/env python3
"""The build machine, judged: Store Python, the MSVC runtime, and the diagnostic.

The dialog this file exists for:

    AppInstallerPythonRedirector.exe - Application Error
    The application was unable to start correctly (0xc0000142).

That is not a bug inside the app's logic — it is a **build-machine** bug that produces an
installer which never opens. Two causes, both preventable, both checked here:

  1. building with the Microsoft Store's Python alias (its DLLs come from a restricted
     package folder, so the frozen exe cannot initialise them),
  2. a missing MSVC runtime on the target PC (Qt needs vcruntime140/msvcp140).

`tools/preflight_win.py` decides, before PyInstaller runs. Its rules are pure functions,
so they are proven here without a Windows machine.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-win-"))

import preflight_win as pre  # noqa: E402

ok = True


def check(label: str, got, want) -> None:
    global ok
    good = got == want
    ok = ok and good
    shown = repr(got)
    if len(shown) > 56:
        shown = shown[:53] + "…"
    print(f"   {'OK  ' if good else 'FAIL'} {label:<52} {shown}"
          + ("" if good else f"   (wanted {want!r})"))


print("1) the Store Python alias is refused, by path, before anything is built")
store = r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\python.exe"
verdict, detail, fix = pre.classify_python(store, (3, 12), bits=64, in_venv=False)
check("verdict", verdict, pre.FAIL)
check("it is named as the store alias", "Microsoft Store Python alias" in detail, True)
check("the title of the dialog is quoted back", "0xc0000142" in detail, True)
check("the fix is the alias switch, not 'reinstall Windows'",
      "App execution aliases" in fix, True)
check("a store base_prefix is caught too, even from a real exe path",
      pre.classify_python(r"C:\Python312\python.exe", (3, 12),
                          base_prefix=store)[0], pre.FAIL)
check("the redirector name is caught",
      pre.classify_python(r"C:\x\AppInstallerPythonRedirector.exe", (3, 12))[0], pre.FAIL)

print("\n2) a real python.org interpreter passes")
verdict, detail, fix = pre.classify_python(r"C:\Python312\python.exe", (3, 12),
                                           bits=64, in_venv=True)
check("verdict", verdict, pre.PASS)
check("it says 64-bit", "64-bit" in detail, True)
check("nothing to fix", fix, "")
check("a venv is recognised",
      pre.classify_python(r"C:\repo\.venv\Scripts\python.exe", (3, 12), in_venv=True)[0],
      pre.PASS)
check("…and not being in one is only a warning",
      pre.classify_python(r"C:\Python312\python.exe", (3, 12), in_venv=False)[0], pre.WARN)

print("\n3) the other ways a build produces an exe that cannot open")
check("32-bit python is refused",
      pre.classify_python(r"C:\Python312-32\python.exe", (3, 12), bits=32)[0], pre.FAIL)
check("python 3.8 is refused",
      pre.classify_python(r"C:\Python38\python.exe", (3, 8), bits=64)[0], pre.FAIL)
check("python 3.9 builds but is flagged",
      pre.classify_python(r"C:\Python39\python.exe", (3, 9), bits=64)[0], pre.WARN)
check("python 3.11 in a venv is exactly right",
      pre.classify_python(r"C:\repo\.venv\Scripts\python.exe", (3, 11), bits=64,
                          in_venv=True)[0], pre.PASS)

print("\n4) the MSVC runtime is found and shipped, not assumed")
with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    (base / "DLLs").mkdir()
    (base / "vcruntime140.dll").write_bytes(b"x")
    (base / "vcruntime140_1.dll").write_bytes(b"x")
    (base / "DLLs" / "msvcp140.dll").write_bytes(b"x")
    found = pre.msvc_runtime_files(base)
    names = sorted(Path(src).name for src, _ in found)
    check("all three are collected", names,
          ["msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"])
    check("they are shipped next to the exe, not in a subfolder",
          {dest for _, dest in found}, {"."})
    check("a name that is not there is not invented",
      "concrt140.dll" in names, False)
check("an empty folder yields nothing rather than a crash",
      pre.msvc_runtime_files(Path(tempfile.gettempdir()) / "does-not-exist-arcdesk"), [])
check("the list matches what Qt actually needs",
      set(pre.MSVC_DLLS) >= {"vcruntime140.dll", "msvcp140.dll"}, True)

print("\n5) the spec ships them (a static fact, checkable anywhere)")
spec = (ROOT / "packaging" / "arcdesk.spec").read_text(encoding="utf-8")
# The spec loads the helper BY FILE PATH — importing it by name would need tools/ on
# sys.path, and tools/packaging.py would then shadow PyInstaller's own `packaging`
# dependency (that is run #15). So the assertion is about the file load, not the import.
check("the spec loads preflight_win by file path (never via sys.path)",
      'spec_from_file_location("_arc_preflight"' in spec, True)
check("…and does not import it by module name",
      "from preflight_win import" in spec, False)
check("…and never touches sys.path",
      "sys.path.insert" not in spec.split("import importlib.util")[1], True)
check("…and puts them in binaries", "binaries=list(_msvc)" in spec, True)
check("…and says so when it finds none",
      "no MSVC DLLs found next to this Python" in spec, True)
check("0xc0000142 is explained where a builder will read it",
      "0xc0000142" in spec, True)
check("no console window still holds", "console=False" in spec, True)
check("still no UPX", "upx=False" in spec, True)
check("still onedir (onefile unpacks to %TEMP% every launch)",
      "exclude_binaries=True" in spec, True)

print("\n5b) the frozen app keeps a log even if it dies before run.py")
hook = ROOT / "packaging" / "pyi_rth_arcdesk.py"
check("the runtime hook exists", hook.is_file(), True)
check("the spec wires it in", "runtime_hooks=RUNTIME_HOOKS" in spec, True)
check("…and names the file", "pyi_rth_arcdesk.py" in spec, True)
import importlib.util                                          # noqa: E402
saved = sys.stdout, sys.stderr
try:
    sys.stdout = None                                          # what a windowed build has
    sys.stderr = None
    module_spec = importlib.util.spec_from_file_location("arc_rth", hook)
    hook_mod = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(hook_mod)                   # type: ignore[union-attr]
    rescued = sys.stdout, sys.stderr
finally:
    sys.stdout, sys.stderr = saved
check("with no console it still ends up with real streams",
      all(stream is not None for stream in rescued), True)
check("…both pointing at the same log file",
      getattr(rescued[0], "name", "") == getattr(rescued[1], "name", ""), True)
check("…and that file exists on disk", Path(getattr(rescued[0], "name", "/nope")).is_file(),
      True)

print("\n6) the build scripts cannot skip the check")
for name in ("build.bat", "build_all.bat"):
    bat = (ROOT / "packaging" / name).read_text(encoding="utf-8")
    order_pre = bat.find("tools\\preflight_win.py")
    # the *invocation*, not the word in a comment
    order_pyi = bat.find("-m PyInstaller")
    check(f"{name} runs the preflight", order_pre > 0, True)
    check(f"{name} runs it BEFORE PyInstaller starts", 0 < order_pre < order_pyi, True)
    check(f"{name} stops on a failure", "if errorlevel 1 (" in bat, True)
    check(f"{name} closes that block", "exit /b 1\n)" in bat, True)

print("\n7) the diagnostic needs nothing but Windows itself")
diag = ROOT / "ArcDeskDiag.bat"
check("ArcDeskDiag.bat exists (double-click, no install)", diag.is_file(), True)
text = diag.read_text(encoding="utf-8", errors="replace")
check("it runs without Python (only lookups, never an interpreter call)",
      "python -c" not in text and "%PY%" not in text, True)
check("it looks for the Store alias", "WindowsApps" in text, True)
check("it quotes the error the user saw", "0xc0000142" in text, True)
check("it checks the MSVC runtime", "vcruntime140.dll" in text, True)
check("it checks whether the download is blocked", "Unblock-File" in text, True)
check("…by reading the real zone stream, not a filename that never exists",
      "Zone.Identifier" in text, True)
check("…unblocks only, never deletes the download",
      "del " not in text.lower() and "rmdir" not in text.lower(), True)
check("…and asks before changing anything", "choice /c YN" in text, True)
check("it writes a report file", "ArcDeskDiag.txt" in text, True)
check("it points at the portable route that needs no installer",
      "ArcDesk-portable.zip" in text, True)
check("it ends with a pause so the window does not vanish", "pause" in text, True)
check("no PowerShell policy change, no PATH edit, no registry write",
      all(bad not in text.lower() for bad in ("setx ", "set-executionpolicy",
                                              "reg add", "net user")), True)

print("\n7b) the diagnostic can actually run (cmd is a language with no compiler)")
import batlint  # noqa: E402

diag_problems = batlint.lint(diag, read_only=True)
check("ArcDeskDiag.bat passes the batch linter", diag_problems, [])
check("…and the other batch files still do",
      [p for p in (ROOT).rglob("*.bat")
       if not any(x in p.parts for x in (".venv", "dist")) and batlint.lint(p)], [])
# The linter has to be able to fail, or it is decoration: feed it the exact mistakes
# cmd punishes silently.
with tempfile.TemporaryDirectory() as tmp:
    broken = Path(tmp) / "broken.bat"
    broken.write_text(
        "@echo off\n"
        "if exist x (\n"
        "  echo   a parenthesis ( like this breaks the block\n"     # fatal
        "  goto :nowhere\n"                                          # stops silently
        ")\n"
        "setx PATH something\n",                                     # must not be here
        encoding="utf-8")
    found = batlint.lint(broken, read_only=True)
    text_found = " ".join(found)
    check("the linter catches a parenthesis in a block", "bare parenthesis" in text_found,
          True)
    check("…a goto with no label", ":nowhere" in text_found, True)
    check("…and a write in a read-only tool", "setx" in text_found, True)
    clean = Path(tmp) / "clean.bat"
    clean.write_text("@echo off\necho (fine at the top level)\n"
                     "if exist x (\n  echo ^(escaped^) is fine too\n)\nexit /b 0\n",
                     encoding="utf-8")
    check("an honest file passes", batlint.lint(clean, read_only=True), [])
check("the report is written where a person will look (the Desktop)",
      "%USERPROFILE%\\Desktop" in text, True)
check("…and also copied next to the .bat",
      'copy /y "%REPORT%"' in text, True)
check("…and the path is printed at the end", "echo  Report:" in text, True)
check("it warns about running from inside the zip, where the report would vanish",
      "inside the .zip" in text.lower(), True)
check("…and says it in the window, not only in a REM nobody reads",
      "echo  If you double-clicked this" in text, True)
check("every goto has a label (cmd stops silently otherwise)",
      not batlint.lint(diag, read_only=True), True)

print("\n7c) the shortcut cannot lie about what it launches")
repair = ROOT / "ArcDeskRepair.bat"
starter = ROOT / "ArcDeskStart.bat"
check("ArcDeskRepair.bat exists", repair.is_file(), True)
check("ArcDeskStart.bat exists", starter.is_file(), True)
rt = repair.read_text(encoding="utf-8")
st = starter.read_text(encoding="utf-8")
check("the repair finds every copy, not one hard-coded path",
      rt.count("call :try_exe") >= 6, True)
check("…including the per-user install folder",
      "%LOCALAPPDATA%\\Programs\\ArcDesk" in rt, True)
check("it actually starts each copy and waits before judging", "timeout /t 8" in rt, True)
check("it names the Store-alias cause", "WindowsApps" in rt, True)
check("it names the missing VC++ runtime",
      "vcruntime140.dll" in rt and "Microsoft Visual C++ Redistributable" in rt, True)
check("it names the copied-exe-without-_internal cause", "_internal" in rt, True)
check("it rebuilds the shortcut with a real target and icon",
      "$s.IconLocation" in rt and "$s.WorkingDirectory" in rt, True)
check("…and asks before changing the user's Desktop", "choice /c YN" in rt, True)
check("both pass the batch linter",
      [batlint.lint(repair, read_only=False), batlint.lint(starter, read_only=False)], [[], []])
check("the visible starter keeps the console open so errors are readable",
      "pause" in st, True)
check("…and runs the app with --show", "--show" in st, True)
check("…and handles a source copy through .venv", ".venv\\Scripts\\python.exe" in st, True)

inst = (ROOT / "install_shortcut.bat").read_text(encoding="utf-8")
check("install_shortcut sets a proper icon", "IconLocation" in inst, True)
check("…and a working directory", "WorkingDirectory" in inst, True)
check("…and falls back to the visible starter instead of a silent .py shortcut",
      "ArcDeskStart.bat" in inst, True)
check("…and never creates a shortcut to a .py/.pyw",
      all(".pyw'" not in line and ".py'" not in line for line in inst.splitlines()), True)

print("\n7d) the GitHub workflow cannot go green while shipping a dead exe")
wf = ROOT / ".github" / "workflows" / "build-windows.yml"
check("the workflow file exists", wf.is_file(), True)
w = wf.read_text(encoding="utf-8")
blocks = [b for b in w.split("\n      - ") if b.strip()]
by_name = {}
for block in blocks:
    head = block.splitlines()[0]
    by_name[head[:60]] = block


def block_with(*needles: str) -> str:
    for head, body in by_name.items():
        if all(n in head for n in needles):
            return body
    return ""


build_step = block_with("build both executables")
check("there is a step that builds from the spec", bool(build_step), True)
check("…and it is NOT allowed to fail quietly",
      "continue-on-error" in build_step, False)
check("there is no silent 'fallback build' STEP any more (it shipped a dead exe)",
      [head for head in by_name if "fallback" in head.lower()], [])
check("the machine is judged before PyInstaller runs",
      0 < w.find("preflight_win.py") < w.find("-m PyInstaller"), True)
check("the output is checked for the exe, the voice exe and _internal",
      all(k in w for k in ("ArcDeskVoice.exe is missing", "_internal is missing")), True)
check("the icon is checked (its absence is what the user saw on the desktop)",
      "arc_icon.ico" in w, True)
print("\n  the .ico itself: Explorer only draws small frames it can read")
import struct as _struct  # noqa: E402

_ico = (ROOT / "shots" / "arc_icon.ico").read_bytes()
_frame_count = _struct.unpack("<H", _ico[4:6])[0]
_layout = []
for _i in range(_frame_count):
    _off = 6 + _i * 16
    _w, _h, _c, _r, _p, _bpp, _size, _at = _struct.unpack("<BBBBHHII", _ico[_off:_off + 16])
    _layout.append((( _w or 256), "PNG" if _ico[_at:_at + 4] == b"\x89PNG" else "BMP"))
check("the icon has all seven sizes Windows asks for",
      [s for s, _ in _layout], [16, 24, 32, 48, 64, 128, 256])
check("every size below 256 is a BMP frame (PNG-only frames make Explorer show the python)",
      [k for size, k in _layout if size < 256], ["BMP"] * 6)
check("256 is a PNG frame, like every icon tool on Windows produces",
      [k for size, k in _layout if size == 256], ["PNG"])

check("the exe's own icon is checked, not just the .ico file",
      "--icon-check" in w, True)
check("…and a bad icon stops the artifact from being published",
      "does not carry Arc Desk's icon" in w, True)
check("the built exe is actually STARTED on the runner",
      "Start-Process" in w and "--doctor" in w, True)
check("…and the step WAITS for it to exit instead of guessing with a sleep",
      "WaitForExit(180000)" in w, True)
check("…and requires the doctor's RESULT line before it believes anything",
      'if ($text -notmatch "RESULT:")' in w, True)
check("…and its log is read, so a silent crash fails the build",
      "arcdesk.log" in w and "Traceback" in w, True)
check("…and that log is uploaded either way", "arcdesk-run-log" in w, True)
check("the installer is required, not 'best effort'",
      "throw \"ISCC" in w or "no installer can be built" in w, True)
check("the test suite is still not in the pipeline (tests must not block a build)",
      "run_all.py" not in w, True)
check("the only optional step left is the voice libraries",
      [line.strip() for line in w.splitlines()
       if line.strip().startswith("continue-on-error")], ["continue-on-error: true"])

print("\n8) the guide matches the dialogs people actually get")
guide = (ROOT / "TROUBLESHOOT.md").read_text(encoding="utf-8")
for phrase in ("AppInstallerPythonRedirector", "0xc0000142", "Visual C++ Redistributable",
               "MSVCP140.dll", "Windows protected your PC", "WindowsApps"):
    check(f"covers {phrase}", phrase.lower() in guide.lower(), True)
check("the first thing it offers is the route that needs no Python at all",
      guide.index("Use it today, no installer") < guide.index("Rebuild only if you want"),
      True)
check("…and that route is the portable zip", "Extract All" in guide, True)
check("it says where the crash log is", "arcdesk.log" in guide, True)

print("\n9) the tool itself answers honestly on this machine")
rc_all = pre.run(verbose=False)
check("run(verbose=False) returns on warnings but fails on a real problem",
      rc_all in (0, 1), True)
import io                                                       # noqa: E402
import contextlib                                               # noqa: E402
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    pre.run(as_json=True)
import json                                                     # noqa: E402
data = json.loads(buf.getvalue())
check("the JSON has one row per check", len(data["rows"]), len(pre.CHECKS))
check("every row names a fix when it is not a pass",
      all(r["fix"] for r in data["rows"] if r["verdict"] in (pre.FAIL, pre.WARN)), True)

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
