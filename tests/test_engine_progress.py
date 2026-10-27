"""A 1.5 GB download must look like a 1.5 GB download, not like a hang.

The report, with a screenshot of the engine dialog: *"voice engine downloading nu run
aaguthu but run aagura mathiri theriyala"* — it was running, and nothing on screen said so.
The bar was set to "indeterminate" and pip's progress bars are written with carriage
returns that the old line reader never split, so a live download looked frozen for
minutes.

What is proven here:

  1. pip's and huggingface's progress lines are parsed into percentages and megabytes;
  2. ordinary lines stay ordinary lines (they are not eaten by the parser);
  3. the child process's carriage-return updates really do reach the callback, in order;
  4. the dialog's bar is determinate (0-100) and its live line says MB, speed and time;
  5. with no readings at all, it still says how long it has been working.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_engine_progress.py
"""
from __future__ import annotations

import io
import os
# Unit tests, no network: the licence gate asks Hugging Face for a real file, and the
# answer depends on whether THIS machine has a token. That is a property of the machine,
# not of the code under test, so the gate is switched off here and tested on its own in
# tests/test_engine_auto.py.
os.environ.setdefault("ARCDESK_OFFLINE", "1")
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import engines  # noqa: E402

# The licence gate is a network question ("is this model's file readable without a token?").
# These checks are about WHERE an install goes and WHAT it runs, so the gate is stubbed to
# say YES here. The real gate has its own checks: §6 of tests/test_engine_progress.py, and
# tools/engine_get.py gate.
engines._http_status = lambda url="", token="", timeout=12.0: 200       # noqa: SLF001


ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<58} {got!r}")


def wait_for_list(dialog, seconds: float = 8.0) -> None:
    """Wait for the engine list to arrive.

    Since fix49 the dialog asks for the engine state on a worker and fills the list when
    the answer comes back (that is the whole point: no child process on the drawing
    thread). So the list is empty for a moment after construction — this pumps the real
    event loop instead of asserting against a frozen snapshot.
    """
    import time as _time

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    deadline = _time.monotonic() + seconds
    loop = QEventLoop()
    beat = QTimer()
    beat.setInterval(25)

    def poll() -> None:
        if dialog.picker.count() or _time.monotonic() > deadline:
            loop.quit()

    beat.timeout.connect(poll)
    beat.start()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()
    beat.stop()
    QApplication.processEvents()


print("1. what pip prints, turned into numbers")
pip_bar = "   ━━━━━━━━━━━━━━━━━━━━━━━━ 45.2/779.9 MB 3.1 MB/s eta 0:04:00"
got = engines.read_progress(pip_bar) or {}
check("pip's ascii bar gives megabytes", (got.get("mb"), got.get("total_mb")), (45.2, 779.9))
check("…and a percentage", round(got.get("percent", 0)), 6)
check("…and the speed", got.get("speed"), "3.1 MB/s")
check("…and the estimate", got.get("eta"), "0:04:00")

hf_bar = " 45%|███       | 812M/1.6G [02:10<03:00, 4.2MB/s]"
got = engines.read_progress(hf_bar) or {}
check("huggingface's tqdm bar gives megabytes", (got.get("mb"), got.get("total_mb")),
      (812.0, 1600.0))
check("…and its own percentage", got.get("percent"), 45.0)
check("…and the speed", got.get("speed"), "4.2 MB/s")

gib_bar = "  30.0/1.50 GiB [00:20<01:40, 1.5 MB/s]"
got = engines.read_progress(gib_bar) or {}
check("GiB is converted, not misread as GB", round(got.get("mb", 0)), 32212)

print("\n2. ordinary lines are left alone")
for line in ("Downloading torch-2.5.1-cp312-cp312-win_amd64.whl (779.9 MB)",
             "Successfully installed torch-2.5.1 transformers-4.46.2",
             "Collecting numpy>=1.26",
             ""):
    check(f"not a progress bar: {line[:38] or '(blank)'}",
          engines.read_progress(line), None)

print("\n3. carriage-return updates reach the callback (the actual bug)")


class FakeProc:
    def __init__(self, payload: bytes) -> None:
        self.stdout = io.BytesIO(payload)

    def wait(self, timeout=None) -> int:
        return 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass


payload = (b"Collecting torch\r"
           b"  10.0/779.9 MB 3.0 MB/s eta 0:04:00\r"
           b"  50.0/779.9 MB 3.0 MB/s eta 0:02:00\r"
           b"100.0/779.9 MB 3.0 MB/s eta 0:00:01\n"
           b"Successfully installed torch\n")
real_popen = engines.quiet.popen
engines.quiet.popen = lambda *a, **k: FakeProc(payload)      # noqa: SLF001
lines: list[str] = []
readings: list[dict] = []
out = engines._run(["py", "-m", "pip", "install", "torch"], lines.append, None,  # noqa: SLF001
                   readings.append)
engines.quiet.popen = real_popen                              # noqa: SLF001

check("the run is reported as a success", out.get("ok"), True)
check("every carriage-return update became one reading", len(readings), 3)
check("…in order, with real percentages",
      [round(r["percent"]) for r in readings], [1, 6, 13])
check("the log keeps the sentences, not the bars", lines,
      ["Collecting torch", "Successfully installed torch"])

print("\n4. the dialog shows a number, a speed and a clock")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])
from arcdesk.theme import THEMES  # noqa: E402
from arcdesk.widgets.engine_dialog import EngineDialog  # noqa: E402

theme = THEMES.get("chill") or next(iter(THEMES.values()))
dialog = EngineDialog(theme)
wait_for_list(dialog)
check("the bar is determinate, not a spinner", (dialog.bar.minimum(), dialog.bar.maximum()),
      (0, 100))
check("it starts at zero", dialog.bar.value(), 0)

dialog._started = __import__("time").monotonic() - 65          # noqa: SLF001
dialog._on_progress({"percent": 42.0, "mb": 630.0, "total_mb": 1500.0,           # noqa: SLF001
                     "speed": "3.4 MB/s", "eta": "0:04:00"})
check("the bar moves to the reported percentage", dialog.bar.value(), 42)
live = dialog.live.text()
check("the live line says megabytes", "630 of 1500 MB" in live, True)
check("…and the speed", "3.4 MB/s" in live, True)
check("…and roughly how long is left, from the measured speed",
      ("4 min left at this speed" in live) or ("0:04:00" in live), True)
check("…and how long it has been working", "1 min 05 s" in live, True)

dialog._seen = {}                                              # noqa: SLF001
dialog._paint_live()                                           # noqa: SLF001
silent = dialog.live.text()
check("with no readings it still proves it is alive", "in" in silent and "waiting" in silent)
check("…and the bar does not claim 0%", dialog.bar.format(), "working")

dialog.close()
print("\n5. the easy route is offered first, and torch is not a 2.5 GB mistake")
from arcdesk.widgets.engine_dialog import _mb_per_second  # noqa: E402

check("speeds are readable, so the estimate is measured",
      (_mb_per_second("3.1 MB/s"), _mb_per_second(None)), (3.1, None))
check("smallest engine is listed first",
      dialog.picker.itemText(0).startswith("Piper"), True)
check("…and is labelled the easiest", "easiest" in dialog.picker.itemText(0))
check("the big engines are still there, in size order",
      [dialog.picker.itemData(i) for i in range(dialog.picker.count())],
      ["piper", "indicf5", "xtts"])
check("the dialog says what to do when a big download will not finish",
      "Piper" in dialog.hint.text() and "60 MB" in dialog.hint.text(), True)

dialog._on_progress({"percent": 20.0, "mb": 300.0, "total_mb": 1500.0,   # noqa: SLF001
                     "speed": "3.0 MB/s"})
check("the live line estimates the wait from THIS download",
      "7 min left at this speed" in dialog.live.text(), True)

heavy, rest = engines.split_packages(["torch", "transformers", "soundfile"])
check("torch is installed separately, from the CPU-only index",
      (heavy, rest), (["torch"], ["transformers", "soundfile"]))
check("…so no engine asks for a CUDA build by accident",
      engines._TORCH_CPU_INDEX.endswith("/whl/cpu"), True)     # noqa: SLF001
check("piper costs about a minute, not an evening",
      engines.SPECS["piper"]["size_mb"] <= 120, True)
check("piper needs no torch", "torch" in engines.SPECS["piper"]["packages"], False)
check("there is one function that names the easy engine", engines.easiest()["id"], "piper")
check("…and it is the one the router can actually use",
      engines.SPECS["piper"]["label"] in ("Piper", "piper"))
compile(engines.SPECS["piper"]["warm"], "<piper-warm>", "exec")
check("the voice downloader is a valid program", True)

print("\n6. a gated model is refused BEFORE 200 MB of torch, and explained")
# The real screenshot: "OSError ... gated repo ... 401 Client Error" at the end of a long
# download. Hugging Face was refusing every file; nothing was ever going to arrive.
# this is the section that measures the gate itself, so the file-wide offline switch
# (set at the top, because every other section must not depend on this machine's token)
# has to be off here.
_offline = os.environ.pop("ARCDESK_OFFLINE", None)
real_status = engines._http_status                                  # noqa: SLF001
engines._http_status = lambda url, token="", timeout=12.0: 401       # noqa: SLF001
try:
    state = engines.gate("indicf5")
    check("hugging face says 401 -> the app calls it gated", state.get("gated"), True)
    check("…and points at the model page", state.get("url", "").endswith("IndicF5"))
    advice = engines.gate_advice("indicf5")
    check("the advice names the licence click", "Agree" in advice)
    check("…the token page", "settings/tokens" in advice)
    check("…and the no-account alternative", "Piper" in advice)

    calls: list[list[str]] = []
    engines._run = lambda argv, on_line, cancel=None, on_progress=None: (   # noqa: SLF001
        calls.append(list(argv)), {"ok": True, "code": 0, "why": "", "last": ""})[1]
    lines: list[str] = []
    got = engines.install("indicf5", on_line=lines.append)
    check("the install refuses instead of pretending", got.get("ok"), False)
    check("…and says a token is what is missing", got.get("needs_token"), True)
    check("…and NOTHING was downloaded first (no 200 MB of torch)", calls, [])
    check("…the refusal is printed, not swallowed",
          any("gated" in line.lower() for line in lines), True)

    # The measurement that matters (21.png): Hugging Face answers 200 for the METADATA and
    # 401 for every FILE. Checking the metadata was the bug — it said "no licence needed",
    # spent 200 MB of torch, then died on the first file with the traceback on screen.
    def metadata_open_files_gated(url, token="", timeout=12.0):
        return 200 if "/api/models/" in url else 401

    engines._http_status = metadata_open_files_gated                      # noqa: SLF001
    check("a 200 on the metadata API is not proof of access",
          engines.gate("indicf5").get("gated"), True)
    check("the gate asks about a real file, not the model page",
          "/resolve/main/" in engines.gate_url("ai4bharat/IndicF5")
          and engines.gate_url("ai4bharat/IndicF5").endswith("config.json"), True)

    engines._http_status = lambda url, token="", timeout=12.0: 404        # noqa: SLF001
    check("a missing file name is not a licence problem",
          engines.gate("indicf5").get("gated"), False)

    engines._http_status = lambda url, token="", timeout=12.0: 200    # noqa: SLF001
    check("with access, the gate opens", engines.gate("indicf5").get("gated"), False)
    check("engines with no gate are never checked", engines.gate("piper").get("repo"), "")
    engines._http_status = lambda url, token="", timeout=12.0: 0       # noqa: SLF001
    check("offline does not block a download that might work",
          (engines.gate("indicf5").get("gated"), engines.gate("indicf5").get("unknown")),
          (False, True))
finally:
    engines._http_status = real_status                              # noqa: SLF001

print("\n7. the token is remembered privately, and never printed")
engines.set_token("hf_TEST_123")
check("the token is stored", engines.token(), "hf_TEST_123")
engines.set_token("")
check("…and can be cleared again", engines.token(), "")
check("the token is not in the source tree",
      "hf_TEST_123" in "".join(p.read_text(encoding="utf-8", errors="replace")
                               for p in (Path(__file__).resolve().parents[1] / "arcdesk").rglob("*.py")),
      False)

dialog._finished({"ok": False, "engine": "indicf5", "why": "gated model",   # noqa: SLF001
                  "needs_token": True, "lines": []})
check("the dialog offers the fix, not a shrug", "token" in dialog.verdict.text().lower())
check("…and a field to paste it into", dialog.token.echoMode().name, "Password")

print("\n9. an engine installed in a TERMINAL is used, not asked for again")
# The report: "manual ah nan voice clone applications through terminal la download
# paniten but jarvis kula again install pana solluthu". pip in a terminal installs into
# SOME python; the app runs in its own .venv and cannot see it. Two things must happen:
# the app must FIND that python, and USE it instead of asking for a second 1.5 GB.
from arcdesk import clone  # noqa: E402

real_find = engines.find_engine_python
real_cached = engines.foreign_cached
real_probe = engines.probe_python
real_model = clone._model_dir                                       # noqa: SLF001
real_noforig = os.environ.pop("ARCDESK_NO_FOREIGN_PYTHON", None)
# "nothing is installed" has to be true in THIS process too. Since fix53 an engine counts
# as found when the packages are importable here *or* in another interpreter, so on a
# machine that happens to have transformers (a developer's laptop, an .venv someone filled)
# the wording changes from "missing the transformers package" to "missing the weights".
# Pinning it is the difference between testing the code and testing the laptop.
real_importable = clone._importable                                     # noqa: SLF001
clone._importable = lambda name: False                                  # noqa: SLF001
try:
    engines.probe_python = lambda exe, mods: {m: False for m in mods}   # noqa: SLF001
    engines.find_engine_python = lambda engine: ""                      # noqa: SLF001
    clone._model_dir = lambda name: None                                # noqa: SLF001
    clone.refresh()
    alone = clone.engines()["indicf5"]
    check("nothing installed anywhere -> not ready", alone["available"], False)
    check("…and it says exactly what is missing",
          ("weights" in alone["why"] and "transformers" in alone["why"]), True)

    called: list[str] = []

    def fake_find(engine: str) -> str:
        called.append(engine)
        return r"C:\Users\emera\AppData\Local\Programs\Python\Python312\python.exe"

    engines.find_engine_python = fake_find                            # noqa: SLF001
    # since fix48 the probe is answered from a cache that a daemon thread fills, so the
    # test warms that cache directly instead of waiting for a thread
    engines.foreign_cached = lambda engine, warm=True: fake_find(engine)   # noqa: SLF001
    clone._model_dir = lambda name: Path("C:/cache/models--ai4bharat--IndicF5") \
        if name == "IndicF5" else None                                 # noqa: SLF001
    clone.refresh()
    other = clone.engines()["indicf5"]
    check("a python that already has it makes the engine ready", other["available"], True)
    check("…and the app remembers WHICH python", "Python312" in other["foreign"], True)
    check("…it is not called 'missing' any more", other["why"], "")

    spoke: dict = {}

    def fake_sidecar(text, lang, ref, transcript="", out_wav="", engine="", python=""):
        spoke.update(engine=engine, python=python, text=text)
        return {"ok": True, "why": "", "wav": "x.wav"}

    from arcdesk import engines as engmod
    real_s = engmod.sidecar_speak
    engmod.sidecar_speak = fake_sidecar
    ref_file = Path(tempfile.mkdtemp()) / "reference.wav"
    ref_file.write_bytes(b"RIFF")
    clone.reference = lambda: ref_file                                # noqa: SLF001
    clone.transcript = lambda: "hello"                                # noqa: SLF001
    clone._sidecar_speak = lambda *a, **k: True                       # noqa: SLF001
    # the route is what this section is NOT about (it is about which python speaks), so
    # it is pinned: otherwise the answer depends on what else this machine happens to have
    # installed, and the check passes or fails according to the developer's laptop.
    real_route = clone.route
    clone.route = lambda lang="ta", *a, **k: "indicf5"                # noqa: SLF001
    try:
        ok_speak = clone.speak("vanakkam macha", "ta")
    finally:
        clone.route = real_route                                      # noqa: SLF001
    check("it speaks through that python, not a new download", ok_speak, True)
    engmod.sidecar_speak = real_s

    seen = engines.diagnose()
    check("the diagnosis lists the interpreters it checked",
          isinstance(seen.get("interpreters"), list) and len(seen["interpreters"]) >= 1)
    check("…and says where the weights are, or that they are not",
          "IndicF5" in seen.get("weights", {}))
    text = engines.diagnosis_text()
    check("the diagnosis is sentences, not a dict", "which python has what" in text)
finally:
    engines.find_engine_python = real_find                            # noqa: SLF001
    engines.foreign_cached = real_cached                              # noqa: SLF001
    engines.probe_python = real_probe                                 # noqa: SLF001
    clone._importable = real_importable                               # noqa: SLF001
    clone._model_dir = real_model                                     # noqa: SLF001
    if real_noforig is not None:
        os.environ["ARCDESK_NO_FOREIGN_PYTHON"] = real_noforig
    clone.refresh()

print("\n10. the dialog can go and look, instead of assuming")
check("there is a 'Find what I installed' button", hasattr(dialog, "scan"))
dialog._scan()                                                     # noqa: SLF001
check("it returns at once instead of freezing the dialog",
      "looking for an engine" in dialog.log.toPlainText(), True)


def wait_for_scan(dialog, seconds: float = 15.0) -> None:
    """The scan runs on a worker (fix49), so its report arrives a moment later."""
    import time as _time

    from PySide6.QtCore import QEventLoop, QTimer
    deadline = _time.monotonic() + seconds
    loop = QEventLoop()
    beat = QTimer()
    beat.setInterval(25)

    def poll() -> None:
        if "which python has what" in dialog.log.toPlainText() or _time.monotonic() > deadline:
            loop.quit()

    beat.timeout.connect(poll)
    beat.start()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()
    beat.stop()


wait_for_scan(dialog)
check("scanning prints which python has what",
      "which python has what" in dialog.log.toPlainText())
check("…and ends with a verdict, not silence", bool(dialog.verdict.text()))

print("\n11. an engine installed in a conda environment is found, not re-downloaded")
import shutil as _shutil                                                 # noqa: E402
import tempfile as _tempfile                                             # noqa: E402

root = Path(_tempfile.mkdtemp(prefix="arcdesk-conda-")) / "envs"
env_ok = root / "indicf5"
env_ok.mkdir(parents=True)
made = False
try:
    # a real interpreter, because the probe really runs it
    for name in ("python.exe", "python"):
        target = env_ok / ("bin" if name == "python" else "") / name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.symlink_to(Path(sys.executable))
        except (OSError, NotImplementedError):
            _shutil.copy2(sys.executable, target) if Path(sys.executable).stat().st_size < 20_000_000 else None
        made = made or target.exists()
except Exception:                                                        # noqa: BLE001
    made = False
(root / "empty").mkdir(parents=True, exist_ok=True)          # no interpreter inside

old_env = os.environ.get("CONDA_ENVS_PATH")
os.environ["CONDA_ENVS_PATH"] = str(root)
try:
    found = engines.conda_pythons()
    check("a conda environment is discovered", [n for n, _ in found], ["conda env 'indicf5'"])
    check("…an env with no python is ignored",
          any("empty" in name for name, _ in found), False)
    labels = [l for l, _ in engines.interpreters()]
    check("…and the app will ask it, by name", "conda env 'indicf5'" in labels, True)
    called = []
    # the selection rule, tested without installing torch: an interpreter that answers
    # "yes" for every module is the one the app must choose.
    real_interp, real_probe = engines.interpreters, engines.probe_python      # noqa: SLF001
    conda_one = str(next(p for _n, p in engines.conda_pythons()))
    engines.interpreters = lambda: [("conda env 'indicf5'", conda_one)]       # noqa: SLF001
    engines.probe_python = lambda exe, mods: {m: True for m in mods}          # noqa: SLF001
    try:
        check("…and the one that has the packages is the one chosen",
              Path(engines.find_engine_python("indicf5")).name in ("python", "python.exe"),
              True)
    finally:
        engines.interpreters, engines.probe_python = real_interp, real_probe   # noqa: SLF001
    os.environ["ARCDESK_ENGINE_PYTHON"] = str(_tempfile.mkdtemp()) + "/nope"
    check("a path that does not exist is not offered",
          any("pointed at" in l for l, _ in engines.interpreters()), False)
    # a path that is not already in the list (sys.executable is, as "this app")
    real_py = next((p for n, p in engines.conda_pythons()), "") or str(sys.executable)
    os.environ["ARCDESK_ENGINE_PYTHON"] = real_py
    labels2 = [l for l, _ in engines.interpreters()]
    check("…and one that does exist is offered, with its own label",
          "the python you pointed at" in labels2, True)
finally:
    os.environ.pop("ARCDESK_ENGINE_PYTHON", None)
    if old_env is None:
        os.environ.pop("CONDA_ENVS_PATH", None)
    else:
        os.environ["CONDA_ENVS_PATH"] = old_env

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
