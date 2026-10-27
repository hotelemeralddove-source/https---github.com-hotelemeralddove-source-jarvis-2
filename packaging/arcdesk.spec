# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — TWO binaries, one folder.

    ArcDesk.exe       the window, the HUD, magic mode, charms            (run.py)
    ArcDeskVoice.exe  the ears: microphone, wake word, speech           (arc_daemon.py)

Build with:  packaging\\build.bat      (never call PyInstaller directly; build.bat
                                      runs the static pre-flight first)

Design notes that matter:

  * Modules are collected with collect_submodules("arcdesk"). A hand-written list is
    how a packaged app imports fine and then dies on the one screen you only open
    once. tools/packaging.py FAILS the build if a hand-written list ever comes back.
  * Two EXEs on purpose: a microphone and a speech model never share a process with
    the Qt window. That separation is where the memory budget comes from.
  * onedir, not onefile: onefile unpacks itself to %TEMP% on every launch.
  * upx=False: UPX compression is the single most common cause of antivirus
    false-positives on PyInstaller output. A slightly bigger folder is worth it.
  * This directory is named `packaging/`, NOT `build/`: some tooling (and this
    project's own workspace snapshots) treats a folder called `build` as disposable.
"""
import sys                      # NOT optional: PyInstaller's spec namespace provides
                               # `os` and the build classes, and nothing else. Without
                               # this line `sys.path.insert(...)` below raised NameError,
                               # PyInstaller exited in 2 seconds, and on GitHub Actions
                               # the "fallback build" then shipped an exe with the default
                               # icon, no data files and no voice exe. Fixes run #14.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# SPECPATH is the folder that holds THIS file, i.e. packaging/. The repo root is its
# parent. (This used to apply .parent twice, which pointed ROOT at the folder *above*
# the repo: PyInstaller then died with "script '.../run.py' not found". It was found by
# actually running the build, which is the only way that class of bug shows up.)
PACKAGING = Path(SPECPATH).resolve()
ROOT = PACKAGING.parent
PKG = ROOT / "arcdesk"
if not (ROOT / "run.py").is_file():
    raise SystemExit(
        f"[spec] cannot find run.py next to {PACKAGING}\n"
        f"[spec] expected the repo root at {ROOT}\n"
        "[spec] build with: packaging\\build.bat (or python -m PyInstaller "
        "packaging\\arcdesk.spec from the repo root)")

hiddenimports = collect_submodules("arcdesk")
# Imported lazily inside functions, so the static analyser cannot see them.
hiddenimports += [
    "PySide6.QtNetwork", "PySide6.QtSvg",
    "arcdesk.widgets", "arcdesk.widgets.window", "arcdesk.widgets.assistant",
    "arcdesk.widgets.palette", "arcdesk.widgets.settings", "arcdesk.widgets.welcome",
    "arcdesk.widgets.artview", "arcdesk.widgets.aisetup", "arcdesk.ai.tools",
    "arcdesk.ai.lite", "arcdesk.ai.agent", "arcdesk.ai.voice",
]

# The ears. `import vosk` lives inside a function in arc_daemon.py, so static analysis is
# not enough to guarantee it is collected — and an installed app that cannot import vosk
# is an app where "hey jarvis" silently does nothing. Collected here when present, and
# named loudly when not, so the build log answers the question instead of the user.
import importlib.util as _ilu

for _mod in ("vosk", "sounddevice", "openwakeword", "sherpa_onnx"):
    try:
        if _ilu.find_spec(_mod) is not None:
            hiddenimports += collect_submodules(_mod)
            print(f"[spec] ears: bundling {_mod}")
        else:
            print(f"[spec] ears: {_mod} is NOT installed — that part of the ears will "
                  f"be missing from this build")
    except Exception as _exc:                      # noqa: BLE001
        print(f"[spec] ears: could not collect {_mod} ({_exc})")

datas = []
for pattern in ("*.json", "*.png", "*.svg", "*.ico", "*.wav", "*.qm", "*.html"):
    datas += [(str(p), "arcdesk") for p in PKG.rglob(pattern)]

# The generated in-app pages live *inside* arcdesk/ and are picked up by the rglob
# above. This loop only warns, so a page that was never generated cannot slip by
# unnoticed. Repo-root showcase pages (DEMO_PAGE.html, PREVIEW.html) are deliberately
# not shipped inside the app.
# --doctor is a promised feature (README, INSTALL, Settings -> System), and it is a
# plain script that imports only the stdlib and arcdesk. Ship it as data; without this
# the frozen app answers "--doctor" with ModuleNotFoundError.
# tools/clone_speak.py is how the installed app speaks in a cloned voice: the engine
# lives in a private folder and this script is run with that interpreter (see
# arcdesk/engines.py). Without it here the button installs a model and nothing can use it.
CLONE_SPEAK = ROOT / "tools" / "clone_speak.py"
if CLONE_SPEAK.is_file():
    datas += [(str(CLONE_SPEAK), "tools")]
else:
    print("[spec] WARNING: tools/clone_speak.py is missing — cloned replies cannot work")

DOCTOR = ROOT / "tools" / "doctor.py"
if DOCTOR.is_file():
    datas += [(str(DOCTOR), "tools")]
else:
    print("[spec] WARNING: tools/doctor.py is missing — --doctor will not work")

for page in ("KNOWS_PAGE.html", "STUDIO_PAGE.html", "TOOLS_PAGE.html"):
    if (PKG / page).is_file():
        print(f"[spec] bundling arcdesk/{page}")
    else:
        print(f"[spec] WARNING: arcdesk/{page} is missing — run the generator")

icon = str(ROOT / "assets" / "arc_icon.ico")
if not Path(icon).is_file():
    icon = str(ROOT / "shots" / "arc_icon.ico")
icon_arg = icon if Path(icon).is_file() else None
if icon_arg is None:
    # Not a warning: PyInstaller's fallback icon is the reason a desktop shortcut can
    # look like a Python script. tools/preflight_win.py fails the build before this,
    # and this line explains it in the PyInstaller log too.
    print("[spec] WARNING: assets/arc_icon.ico is missing - the exe will carry "
          "PyInstaller's own icon, and the shortcut will NOT look like Arc Desk")

# ---------------------------------------------------------------- MSVC runtime
# 0xc0000142 (STATUS_DLL_INIT_FAILED) is what a frozen PySide6 app says on a machine
# without the Microsoft Visual C++ Redistributable: Qt needs vcruntime140 / msvcp140 and
# Windows only has them in System32 when something else installed them first. PyInstaller
# usually picks them up, "usually" is not a promise, so they are collected on purpose and
# shipped beside the exe. The finder lives in tools/preflight_win.py so it can be tested
# from any platform.
#
# DO NOT put tools/ on sys.path to import it. It was done that way for one build, and it
# broke the build in SIX seconds: tools/packaging.py shadowed the pip package `packaging`
# that PyInstaller itself imports (`import packaging.requirements`), so the isolated
# subprocess died with "No module named 'packaging.requirements'; 'packaging' is not a
# package". A plain file load cannot shadow anything:
import importlib.util as _ilu

try:
    _pf_spec = _ilu.spec_from_file_location("_arc_preflight",
                                            ROOT / "tools" / "preflight_win.py")
    _pf = _ilu.module_from_spec(_pf_spec)
    _pf_spec.loader.exec_module(_pf)               # type: ignore[union-attr]
    _msvc = _pf.msvc_runtime_files(sys.base_prefix)
except Exception as _exc:                          # noqa: BLE001
    print(f"[spec] WARNING: could not look for the MSVC runtime ({_exc})")
    _msvc = []
if _msvc:
    print(f"[spec] runtime: bundling {', '.join(sorted({Path(s).name for s, _ in _msvc}))}")
else:
    print("[spec] runtime: no MSVC DLLs found next to this Python — the exe relies on "
          "the VC++ Redistributable being installed on the target PC (see TROUBLESHOOT.md)")

# Runs before run.py: makes the crash log exist even if the first import fails. A
# windowed build that dies early otherwise leaves literally nothing behind.
_rth = ROOT / "packaging" / "pyi_rth_arcdesk.py"
RUNTIME_HOOKS = [str(_rth)] if _rth.is_file() else []
if not RUNTIME_HOOKS:
    print("[spec] WARNING: packaging/pyi_rth_arcdesk.py is missing — an early crash "
          "would leave no log at all")

# --------------------------------------------------------------- what to leave out
# The app draws with QtCore/QtWidgets/QtGui and nothing else (measured: 88 import lines
# across the package, all three modules). Everything Qt ships beyond that is dead weight:
# WebEngine alone is ~110 MB on Windows and Quick/Qml ~40 MB. requirements.txt pins
# PySide6-Essentials so CI never installs them - but they are one careless
# `pip install PySide6` away (that meta-package pulls the Addons wheel), and the same
# spec would then produce a build nobody asked for. Excluding them makes the size a
# property of this file instead of a property of the machine.
#
# Every entry here is a module the app never imports, so "will it still run?" is answered
# by the frozen doctor plus a real start (both run in this repo), not by hope. If one of
# them is ever actually needed, PyInstaller says so loudly at import time — and step 5 of
# the workflow starts the built exe on Windows and reads its log.
_QT_DEAD = [
    "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel",
    "QtWebSockets", "QtQuick", "QtQuick3D", "QtQuickWidgets", "QtQuickControls2",
    "QtQml", "QtQmlModels", "QtQmlWorkerScript", "Qt3DCore", "Qt3DRender",
    "Qt3DInput", "Qt3DLogic", "Qt3DAnimation", "Qt3DExtras", "QtCharts",
    "QtDataVisualization", "QtGraphs", "QtMultimedia", "QtMultimediaWidgets",
    "QtSpatialAudio", "QtPdf", "QtPdfWidgets", "QtSql", "QtTest", "QtDesigner",
    "QtHelp", "QtUiTools", "QtBluetooth", "QtNfc", "QtPositioning", "QtLocation",
    "QtSensors", "QtSerialPort", "QtSerialBus", "QtRemoteObjects", "QtScxml",
    "QtStateMachine", "QtTextToSpeech", "QtHttpServer", "QtAxContainer",
]
# Python's own dead weight. `unittest`/`pydoc`/`lib2to3`/`idlelib` are development tools;
# `setuptools`/`pip`/`pkg_resources` are build tools; the rest ship with CPython and are
# never reached by this app. Ordered by what actually costs space.
_PY_DEAD = [
    "tkinter", "unittest", "pydoc", "doctest", "lib2to3", "idlelib", "turtledemo",
    "ensurepip", "pip", "setuptools", "pkg_resources", "wheel", "distutils",
    "pytest", "_pytest", "matplotlib", "scipy", "pandas", "IPython", "sympy",
    "notebook", "jupyter", "sphinx", "fontTools", "lxml", "babel", "pygments",
]
EXCLUDES = [f"PySide6.{m}" for m in _QT_DEAD] + _PY_DEAD

common = dict(
    pathex=[str(ROOT)],
    binaries=list(_msvc),
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=RUNTIME_HOOKS,
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

a = Analysis([str(ROOT / "run.py")], **common)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ArcDesk",
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False, disable_windowed_traceback=False,
          icon=icon_arg)

v = Analysis([str(ROOT / "arc_daemon.py")], **common)
voice_pyz = PYZ(v.pure)
voice_exe = EXE(voice_pyz, v.scripts, [], exclude_binaries=True, name="ArcDeskVoice",
                debug=False, bootloader_ignore_signals=False, strip=False,
                upx=False, console=False, disable_windowed_traceback=False,
                icon=icon_arg)

# ONE copy of every shared binary. The voice exe is headless (no Qt at all), but its
# Analysis still drags in whatever its imports touch; COLLECT de-duplicates by name, so
# the folder does not carry two copies of the same DLL.
COLLECT(exe, a.binaries, a.datas, voice_exe, v.binaries, v.datas,
        strip=False, upx=False, name="ArcDesk")

# A tiny provenance file next to the exe, so "which build is this?" has an answer.
import datetime as _dt
import sys as _sys
_out = ROOT / "packaging" / "build_info.txt"
_out.write_text(
    "ArcDesk build\n"
    f"built      : {_dt.datetime.now().isoformat(timespec='seconds')}\n"
    f"python     : {_sys.version.split()[0]}\n"
    f"platform   : {_sys.platform}\n"
    f"modules    : {len(hiddenimports)} hidden imports collected\n"
    f"data files : {len(datas)}\n", encoding="utf-8")
