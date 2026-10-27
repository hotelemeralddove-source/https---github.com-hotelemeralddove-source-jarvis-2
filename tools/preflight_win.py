"""Is this machine able to build a Windows installer that will actually start?

The bug this answers
--------------------
`ArcDeskSetup.exe` (53 MB, built here) double-clicked, and Windows answered:

    AppInstallerPythonRedirector.exe - Application Error
    The application was unable to start correctly (0xc0000142).

Two separate faults hide behind that one dialog, and both are build-machine problems,
not user problems:

1. **`AppInstallerPythonRedirector.exe` is the Microsoft Store's Python alias.** It is
   what `python.exe` resolves to when the only Python on the machine is the Store
   package (or its leftover stub). A PyInstaller build made with that interpreter
   carries DLLs from a package folder with restricted ACLs, and the frozen exe then
   **cannot initialise those DLLs** — which Windows reports as `0xc0000142`
   (`STATUS_DLL_INIT_FAILED`). The build "succeeds" and the result never opens.

2. **`0xc0000142` is also what a frozen app says when the MSVC runtime is missing.**
   PySide6 needs `vcruntime140.dll` / `msvcp140.dll`; on a clean Windows install they
   are not guaranteed to be in `System32`. They must be shipped *next to the exe*.

So this file checks, before PyInstaller is allowed to run:

    python  — real CPython, not the Store alias, 64-bit, new enough
    venv    — an isolated build, so the user's machine stays clean
    runtime — the MSVC DLLs that PySide6 needs are findable and will be bundled
    space   — enough disk for a ~1.2 GB build folder
    paths   — not inside OneDrive (it locks files mid-build; PyInstaller then dies)
    tools   — PyInstaller present, Inno Setup present (or the honest fallback)

Exit code 1 on any FAIL, and every FAIL carries the one action that fixes it, because
"build failed" with no next step is how an afternoon disappears.

Tested from Linux: `classify_python()` and `msvc_runtime_files()` are pure functions,
so the Windows rules are provable without a Windows machine.
"""
from __future__ import annotations

import json
import platform
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"

#: Windows ships these in System32 only when the VC++ Redistributable is installed.
MSVC_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "concrt140.dll")

#: Where the Store puts the App Execution Alias stubs.
STORE_ALIAS_MARKERS = ("windowsapps", "appinstallerpythonredirector",
                       "pythonsoftwarefoundation.python")

MIN_PYTHON = (3, 9)
GOOD_PYTHON = (3, 11)


def _rows() -> list[dict]:
    return []


def classify_python(executable: str, version: tuple[int, int] | None = None,
                    base_prefix: str = "", bits: int = 64,
                    in_venv: bool = False) -> tuple[str, str, str]:
    """Judge a build interpreter. Pure: no filesystem, no OS calls.

    Returns (verdict, what it is, what to do about it). Whether the interpreter is the
    Microsoft Store alias is decided by its *path*, because that is exactly how Windows
    decides: the alias lives in `...\\WindowsApps\\python.exe`.
    """
    low = (executable or "").lower()
    prefix_low = (base_prefix or "").lower()
    shown = executable or "(unknown)"

    if any(marker in low for marker in STORE_ALIAS_MARKERS) or \
       any(marker in prefix_low for marker in STORE_ALIAS_MARKERS):
        return (FAIL,
                f"this is the Microsoft Store Python alias ({shown}). A frozen exe built "
                f"with it fails to start with 0xc0000142",
                "Turn the alias off (Settings > Apps > Advanced app settings > App "
                "execution aliases > python.exe and python3.exe), install Python from "
                "python.org, then run packaging\\build_all.bat again")

    if version is not None and tuple(version) < MIN_PYTHON:
        return (FAIL, f"Python {version[0]}.{version[1]} is too old ({shown})",
                f"Install Python {GOOD_PYTHON[0]}.{GOOD_PYTHON[1]} or newer from python.org")

    if version is not None and tuple(version) < GOOD_PYTHON:
        return (WARN, f"Python {version[0]}.{version[1]} works, but is older than the "
                      f"builds this repo was measured on",
                "Fine to continue. Python 3.11+ is what the size and speed numbers "
                "come from")

    if bits and bits != 64:
        return (FAIL, f"32-bit Python ({shown}) — the Qt wheels here are 64-bit",
                "Install the 64-bit installer from python.org")

    note = "64-bit CPython" + (" in a venv" if in_venv else " (not a venv)")
    if not in_venv:
        return (WARN, f"{note}: everything pip installs lands in your system Python",
                "Fine, but `py -3 -m venv .venv` then running build_all.bat keeps this "
                "repo's packages out of your system Python")
    return (PASS, note, "")


def msvc_runtime_files(base_prefix: str | Path) -> list[tuple[str, str]]:
    """The MSVC runtime DLLs that must ride along with the exe.

    Returns PyInstaller `binaries` entries: (source path, destination folder). Empty
    when the files cannot be found — the caller then *says so* instead of pretending
    the exe will open on a machine without the VC++ Redistributable.
    """
    found: list[tuple[str, str]] = []
    base = Path(base_prefix)
    for folder in (base, base / "DLLs", base / "Library" / "bin"):
        if not folder.is_dir():
            continue
        for name in MSVC_DLLS:
            path = folder / name
            if path.is_file():
                entry = (str(path), ".")
                if entry not in found:
                    found.append(entry)
    return found


def check_python() -> tuple[str, str, str]:
    exe = sys.executable or ""
    version = (sys.version_info.major, sys.version_info.minor)
    bits = struct.calcsize("P") * 8
    base = getattr(sys, "base_prefix", "") or ""
    in_venv = bool(getattr(sys, "prefix", "") != base and base)
    return classify_python(exe, version, base, bits, in_venv)


def check_runtime() -> tuple[str, str, str]:
    found = msvc_runtime_files(getattr(sys, "base_prefix", "") or "")
    names = sorted({Path(src).name for src, _ in found})
    if not found:
        return (WARN, "no MSVC runtime DLLs found next to this Python",
                "Windows almost always has them in System32. The spec bundles them when "
                "they are visible; if the built exe says 0xc0000142, install the "
                "Microsoft Visual C++ Redistributable (x64) and rebuild")
    return (PASS, "will bundle " + ", ".join(names), "")


def check_disk(need_gb: float = 6.0) -> tuple[str, str, str]:
    try:
        free = shutil.disk_usage(str(ROOT)).free / (1024 ** 3)
    except OSError:
        return (INFO, "free disk space unknown", "")
    if free < need_gb:
        return (FAIL, f"{free:.1f} GB free, about {need_gb:.0f} GB is needed for a build",
                "Free some space: packaging\\work alone passes 1 GB, and Inno Setup "
                "compresses a second copy of everything")
    return (PASS, f"{free:.1f} GB free", "")


def check_path() -> tuple[str, str, str]:
    here = str(ROOT).lower()
    if "onedrive" in here:
        return (WARN, "this folder is inside OneDrive",
                "OneDrive locks files while it uploads them, and PyInstaller then fails "
                "mid-build with a permission error. Move the repo to C:\\ArcDesk")
    if " " in here:
        return (INFO, "the path contains a space",
                "It works (everything is quoted), just slower to read in logs")
    if len(str(ROOT)) > 110:
        return (WARN, f"the path is {len(str(ROOT))} characters long",
                "Windows stops at 260 unless long paths are enabled. Move the repo "
                "closer to C:\\")
    return (PASS, str(ROOT), "")


def check_pyinstaller() -> tuple[str, str, str]:
    try:
        import PyInstaller  # noqa: F401
        from PyInstaller import __version__ as v
    except Exception:                                   # noqa: BLE001
        return (FAIL, "PyInstaller is not installed for this interpreter",
                "python -m pip install pyinstaller")
    return (PASS, f"PyInstaller {v}", "")


def check_qt() -> tuple[str, str, str]:
    try:
        import PySide6
        from PySide6 import __version__ as v
    except Exception:                                   # noqa: BLE001
        return (FAIL, "PySide6 is not installed for this interpreter",
                "python -m pip install -r requirements.txt")
    return (PASS, f"PySide6 {v}", "")



# --------------------------------------------------------------- the exe's own icon
# PyInstaller applies `icon=` with UpdateResource and writes each image of the .ico
# VERBATIM as an RT_ICON resource (PyInstaller/utils/win32/icon.py: `file.read(
# e.dwBytesInRes)`). So "does this exe carry Arc Desk's icon" is answerable by looking
# for those exact bytes in the .exe file - no Windows API, no reading resources.
#
# Why bother: when the icon is not applied, PyInstaller substitutes its own
# (a yellow python over a white page on a blue floppy). Run #14 shipped exactly that
# and the user's desktop shortcut showed a Python picture, which is a fair thing to
# rage about. A file-level check is the only way to catch it before the artifact is
# published.
def ico_images(ico_path) -> list[bytes]:
    """Every image blob inside a .ico, the way PyInstaller reads them."""
    import struct
    data = Path(ico_path).read_bytes()
    if len(data) < 6 or data[:4] != b"\x00\x00\x01\x00":
        raise ValueError(f"{ico_path} is not a .ico file")
    count = struct.unpack("<H", data[4:6])[0]
    images = []
    for i in range(count):
        off = 6 + i * 16
        _w, _h, _c, _r, _p, _bpp, size, offset = struct.unpack("<BBBBHHII",
                                                              data[off:off + 16])
        images.append(data[offset:offset + size])
    return images


def icon_embedded(exe_path, ico_path) -> tuple[bool, str]:
    """Is Arc Desk's icon inside this exe, or is it PyInstaller's default?

    Returns (ok, sentence). ok is False when the exe carries none of the icon, and also
    when the exe is missing or the .ico cannot be read - an unreadable icon is not a pass.
    """
    exe = Path(exe_path)
    if not exe.is_file():
        return False, f"{exe} does not exist"
    try:
        images = ico_images(ico_path)
    except (OSError, ValueError) as exc:
        return False, f"cannot read {ico_path}: {exc}"
    if not images:
        return False, f"{ico_path} contains no images"
    blob = exe.read_bytes()
    hits = sum(1 for image in images if image and image in blob)
    biggest = max(images, key=len)
    if biggest in blob:
        return True, (f"{exe.name} carries Arc Desk's icon "
                      f"({hits} of {len(images)} image sizes found inside the exe)")
    return False, (f"{exe.name} does NOT carry shots/arc_icon.ico - it is wearing "
                   f"PyInstaller's default icon (the yellow python on a page). 0 of "
                   f"{len(images)} image sizes found in {len(blob) // 1024} KB. The "
                   f"desktop shortcut will look like a Python script")


def check_inno() -> tuple[str, str, str]:
    for base in (r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                 r"C:\Program Files\Inno Setup 6\ISCC.exe"):
        if Path(base).is_file():
            return (PASS, base, "")
    if sys.platform != "win32":
        return (INFO, "not a Windows machine — the installer is compiled there, not here",
                "")
    return (WARN, "Inno Setup 6 not found — the .exe installer cannot be compiled",
            "winget install JRSoftware.InnoSetup   (free). The app still builds, and "
            "dist\\ArcDesk\\ can be zipped and run as-is")


def check_assets() -> tuple[str, str, str]:
    """The icon is required, not decoration.

    Without `assets/arc_icon.ico` PyInstaller does not complain — it silently uses its
    own icon, so the installed app's desktop shortcut shows a yellow-and-blue Python-ish
    box and the user reasonably concludes they installed a Python script that does not
    run. A missing icon is a build failure for that reason alone.
    """
    needed = {"run.py": ROOT / "run.py", "arc_daemon.py": ROOT / "arc_daemon.py",
              "Inno script": ROOT / "packaging" / "arcdesk.iss"}
    missing = [name for name, path in needed.items() if not path.is_file()]
    icon = ROOT / "assets" / "arc_icon.ico"
    if not icon.is_file():
        return (FAIL, "assets/arc_icon.ico is missing",
                "Run  python tools\\make_icon.py  to regenerate it. Without it the "
                "build silently uses PyInstaller's own icon and the desktop shortcut "
                "looks like a Python script")
    if missing:
        return (WARN, "missing: " + ", ".join(missing),
                "The app still builds, but make_installer.bat needs the .iss")
    return (PASS, "run.py, arc_daemon.py, icon, Inno script all present", "")


def _spec_outside(root: Path, stem: str):
    """find_spec for `stem`, with this repo removed from sys.path.

    The repo root itself contains a folder called `packaging/`, so asking from here would
    answer "namespace package, origin None" — which hid the bug this check exists for.
    """
    import importlib.util as ilu
    saved = list(sys.path)
    try:
        keep = []
        for entry in sys.path:
            if entry in ("", "."):
                continue
            try:
                if Path(entry).resolve().is_relative_to(root.resolve()):
                    continue
            except (OSError, ValueError):
                pass
            keep.append(entry)
        sys.path[:] = keep
        return ilu.find_spec(stem)
    except Exception:                                  # noqa: BLE001
        return None
    finally:
        sys.path[:] = saved


#: Files that decide what is on sys.path while PyInstaller or the app runs.
_PATH_DECIDERS = ("packaging/arcdesk.spec", "run.py", "arc_daemon.py",
                  "ArcDesk.pyw", ".github/workflows/build-windows.yml")


def active_shadow_path(root: Path) -> list[str]:
    """Does anything actually put `tools/` (or the root) on sys.path?

    A name collision is harmless until someone adds the folder to the path. This reads the
    files that would do it, so the answer is "is the trap armed", not "does a name clash".
    """
    armed: list[str] = []
    for name in _PATH_DECIDERS:
        path = root / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", "//", ";", "REM")):
                continue
            if "sys.path.insert" in stripped and ("tools" in stripped or '""' in stripped):
                armed.append(f"{name}: {stripped[:80]}")
            if "PYTHONPATH" in stripped and ("tools" in stripped or "pathex" in stripped):
                armed.append(f"{name}: {stripped[:80]}")
    return armed


def shadow_report(root: Path) -> list[tuple[str, str, str]]:
    """Every repo file/folder whose name shadows an importable module.

    Returns (severity, what, why) — severity is FAIL for `tools/*.py` (a folder we may put
    on sys.path) and WARN for a folder at the repo root.
    """
    found: list[tuple[str, str, str]] = []
    candidates: list[tuple[Path, str]] = []
    for path in sorted((root / "tools").glob("*.py")):
        candidates.append((path, FAIL))
    for path in sorted(root.glob("*.py")):
        if path.name not in {"setup.py", "conftest.py"}:
            candidates.append((path, FAIL))
    for path in sorted(p for p in root.iterdir() if p.is_dir()):
        if path.name.startswith((".", "_")) or path.name in {"dists", "dist"}:
            continue
        candidates.append((path, WARN))

    for path, severity in candidates:
        stem = path.stem if path.is_file() else path.name
        if not stem.isidentifier():
            continue
        spec = _spec_outside(root, stem)
        origin = getattr(spec, "origin", None)
        if origin is None or str(origin) == "namespace":
            continue
        origin_path = Path(origin)
        if origin_path.resolve().is_relative_to(root.resolve()):
            continue                      # it is this repo's own module, nothing shadowed
        where = origin_path.parent.name
        kind = "file" if path.is_file() else "folder"
        found.append((severity,
                      f"{path.relative_to(root)} (a {kind}) shadows the module `{stem}` "
                      f"from {where}/",
                      "Rename it, or load it by file path instead of putting its folder "
                      "on sys.path"))
    return found


def check_shadowing() -> tuple[str, str, str]:
    """Does a file in this repo shadow a library PyInstaller imports?

    This bug has already cost two builds. `tools/packaging.py` is *our* checker, but its
    name collides with the pip package `packaging`, which PyInstaller itself imports
    (`import packaging.requirements`). Put `tools/` on `sys.path` — which is what the spec
    did to reach preflight_win.py — and the isolated build subprocess dies in six seconds:

        ModuleNotFoundError: No module named 'packaging.requirements';
        'packaging' is not a package

    A plain file-name collision is enough to be worth refusing, because the alternative is
    finding out from a red build twenty minutes later.
    """
    rows = shadow_report(ROOT)
    armed = active_shadow_path(ROOT)
    if rows and armed:
        names = ", ".join(row[1].split(" (")[0] for row in rows)
        return (FAIL, f"{names} — AND something puts that folder on sys.path "
                      f"({armed[0]}). This is the 6-second build, exactly",
                "Load the helper by file path (importlib.util.spec_from_file_location) "
                "instead of adding tools/ to sys.path, or rename the file. Never leave "
                "both in place")
    if rows:
        names = ", ".join(row[1].split(" (")[0] for row in rows)
        return (INFO, f"latent only: {names} would collide if its folder were put on "
                      f"sys.path — nothing does that today",
                "")
    scripts = len(list((ROOT / "tools").glob("*.py"))) + len(list(ROOT.glob("*.py")))
    return (PASS, f"{scripts} scripts and folders checked, nothing shadows an import", "")


CHECKS = (
    ("Python", check_python),
    ("Shadowing", check_shadowing),
    ("MSVC runtime", check_runtime),
    ("PySide6", check_qt),
    ("PyInstaller", check_pyinstaller),
    ("Inno Setup", check_inno),
    ("Assets", check_assets),
    ("Disk space", check_disk),
    ("Build path", check_path),
)


def run(verbose: bool = True, as_json: bool = False) -> int:
    rows = []
    for name, fn in CHECKS:
        try:
            verdict, detail, fix = fn()
        except Exception as exc:                       # noqa: BLE001
            verdict, detail, fix = WARN, f"check skipped: {type(exc).__name__}: {exc}", ""
        rows.append({"check": name, "verdict": verdict, "detail": detail, "fix": fix})

    fails = [r for r in rows if r["verdict"] == FAIL]
    warns = [r for r in rows if r["verdict"] == WARN]

    if as_json:
        print(json.dumps({"rows": rows, "fail": len(fails), "warn": len(warns)}, indent=2))
    elif verbose:
        print("Arc Desk · before building a Windows installer")
        print("=" * 74)
        icons = {PASS: "[ok]  ", WARN: "[warn]", FAIL: "[FAIL]", INFO: "[info]"}
        for r in rows:
            print(f"{icons.get(r['verdict'], '[?]   ')} {r['check']:<14} {r['detail'][:96]}")
        if fails or warns:
            print("-" * 74)
            for r in fails + warns:
                if r["fix"]:
                    print(f"  {r['check']}: {r['fix']}")
        print("=" * 74)
        if fails:
            print(f"RESULT: {len(fails)} problem(s) to fix before a build is worth starting.")
        elif warns:
            print(f"RESULT: buildable, with {len(warns)} warning(s).")
        else:
            print("RESULT: everything checks out. Run packaging\\build_all.bat.")
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--json" in argv:
        return run(as_json=True)
    if "--quiet" in argv:
        return run(verbose=False)
    if "--icon-check" in argv:
        # used by the Windows workflow AFTER PyInstaller has run: the build machine
        # has the only copy of the exe, so this is the only place it can be judged.
        rest = [a for a in argv if a != "--icon-check"]
        if len(rest) < 2:
            print("usage: preflight_win.py --icon-check <exe> <ico>")
            return 2
        ok, message = icon_embedded(rest[0], rest[1])
        print(("OK   " if ok else "FAIL ") + message)
        return 0 if ok else 1
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
