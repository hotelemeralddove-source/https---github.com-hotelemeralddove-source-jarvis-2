"""The ears — why "hey jarvis" was silent, and the fix that is not a grey sentence

    python tests/test_ears.py

The user's report: *"voice commandku no respond"*. The setup card had already said, in
small grey text, that no wake-word engine was installed — and then offered nothing to do
about it. Four separate things have to be true, and they fail for four different reasons:

    microphone library · wake engine · 40 MB speech model · 30 MB speaker model

This tests that the app names the one that is missing, fixes the ones it can, and never
claims to listen on the strength of a download it did not verify.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-ears-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])

from arcdesk import config, ears  # noqa: E402
from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets.ears_dialog import EarsDialog  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:46]!r}")
    ok &= bool(good)


STATE = {"mic": False, "engine": False, "model": False, "speaker": False}


def fake_status():
    rows = {
        "mic": {"ok": STATE["mic"], "label": "microphone library",
                "found": "sounddevice" if STATE["mic"] else "", "fix": "pip",
                "size_mb": 3, "need": "sounddevice"},
        "engine": {"ok": STATE["engine"], "label": "wake-word engine",
                   "found": "vosk" if STATE["engine"] else "", "fix": "pip",
                   "size_mb": 8, "need": "vosk"},
        "model": {"ok": STATE["model"], "label": "speech model (40 MB)",
                  "found": "x" if STATE["model"] else "", "fix": "download",
                  "size_mb": 40, "need": "vosk-model-small-en-us-0.15"},
        "speaker": {"ok": STATE["speaker"], "label": "speaker model — voice lock (30 MB)",
                    "found": "x" if STATE["speaker"] else "", "fix": "download",
                    "size_mb": 30, "need": "speaker_embedding.onnx"},
    }
    missing = [k for k, v in rows.items() if not v["ok"]]
    ready = all(rows[k]["ok"] for k in ("mic", "engine", "model"))
    return {"rows": rows, "missing": missing, "ready": ready, "wake_possible": ready,
            "sentence": ears.sentence(rows, ready), "pip_possible": True}


print("1) the four requirements, named one by one")
for name in ("mic", "engine", "model", "speaker"):
    STATE[name] = False
real_status = ears.status
ears.status = fake_status
st = fake_status()
check("all four are listed", len(st["rows"]), 4)
check("nothing ready", st["ready"], False)
check("the sentence says what is missing, not 'error'", "Cannot listen yet" in
      st["sentence"], True)
check("…and names the wake engine", "wake-word engine" in st["sentence"], True)

print("\n2) the exact state the user was in: mic yes, engine no")
STATE.update(mic=True, engine=False)
st = fake_status()
check("still not ready", st["ready"], False)
check("the sentence blames the engine, not the microphone",
      "no wake-word engine" in st["sentence"] and "microphone" not in st["sentence"], True)

print("\n3) the fix does the two things that help, and checks again")
CALLS: list[str] = []


def fake_download(on_line, cancel=None):
    CALLS.append("models")
    on_line("speech model: ~40 MB")
    STATE["model"] = True
    STATE["speaker"] = True
    return True


def fake_pip(on_line, cancel=None):
    CALLS.append("pip")
    STATE["mic"] = True
    STATE["engine"] = True
    return True


ears._download_models = fake_download      # noqa: SLF001
ears._pip_install = fake_pip               # noqa: SLF001
ears.pods = lambda: True
ears.model_dir = lambda: "/tmp/m" if STATE["model"] else None
ears.speaker_model = lambda: "/tmp/s" if STATE["speaker"] else None
rows = fake_status()

seen: list[str] = []
res = ears.fix(on_line=seen.append)
check("it finished ready", res["ok"], True)
check("it installed the packages", "pip" in CALLS, True)
check("it downloaded the models", "models" in CALLS, True)
check("the sizes were stated first", any("MB" in l for l in seen), True)
check("it ends by telling you what to say", any("hey jarvis" in l for l in seen), True)
check("ready is re-measured, not assumed", res["status"]["ready"], True)

print("\n4) a cancelled fix is cancelled, never 'ready'")
import threading  # noqa: E402
cancel = threading.Event()
cancel.set()
STATE.update(mic=True, engine=True, model=False, speaker=False)
res = ears.fix(on_line=lambda _l: None, cancel=cancel)
check("not ok", res["ok"], False)
check("it says cancelled", res["why"], "cancelled")

print("\n5) a build that cannot add packages admits it instead of spinning")
# the state of a compiled app with no wake engine: it cannot add one after the fact
STATE.update(mic=True, engine=False, model=True, speaker=True)
ears.status = fake_status
real_pods = ears.pods
ears.pods = lambda: False


def download_that_does_not_fix_the_engine(on_line, cancel=None):
    on_line("speech model: already on disk")
    return True


ears._download_models = download_that_does_not_fix_the_engine   # noqa: SLF001
seen.clear()
res = ears.fix(on_line=seen.append)
check("it did not claim success", res["ok"], False)
check("it names the piece that is still missing",
      "engine" in res["why"], True)
check("and says nothing will pretend to listen",
      any("pretend to listen" in l for l in seen), True)
ears.pods = real_pods
ears._download_models = fake_download          # noqa: SLF001
ears.status = fake_status
STATE.update(mic=True, engine=True, model=True, speaker=True)

print("\n6) the dialog shows ticks, the size, and an honest verdict")
STATE.update(mic=True, engine=False, model=True, speaker=True)
dlg = EarsDialog(get_theme("chill"))
check("four rows on screen", dlg.rows.text().count("✗") + dlg.rows.text().count("✔"), 4)
check("the missing one is a cross", "✗" in dlg.rows.text(), True)
check("the button carries the size to download", "MB" in dlg.go.text(), True)
check("the intro is the same sentence the module produces",
      dlg.intro.text() == fake_status()["sentence"], True)
dlg._finished({"ok": True, "why": ""})
check("success says done", "Done" in dlg.verdict.text(), True)
dlg._finished({"ok": False, "why": "cancelled"})
check("a cancel says stopped", dlg.verdict.text().startswith("Stopped"), True)
dlg._finished({"ok": False, "why": "still missing xxx"})
check("a failure keeps promising nothing", "Not ready" in dlg.verdict.text(), True)

print("\n6b) the speech-model check and the downloader finally agree on one folder")
# This was the user's screenshot: "[arc-voice] already present:
# C:\...\ArcDesk\vosk-model-small-en-us-0.15" and, on the next line, "speech model not
# downloaded". Two folders for one feature. Both now come from voice_ready.
from arcdesk.widgets import voice_ready  # noqa: E402
names = [p.name for p in voice_ready.model_candidates()]
check("the daemon's own folder name is on the list",
      "vosk-model-small-en-us-0.15" in names, True)
check("the older layouts are still accepted",
      any(n in names for n in ("vosk-model", "vosk")), True)
check("the ears module does not keep its own copy of the rule",
      "model_candidates" not in (ROOT / "arcdesk" / "ears.py").read_text(encoding="utf-8"), True)

print("\n7) it is reachable from setup and from Settings")
welcome = (ROOT / "arcdesk" / "widgets" / "welcome.py").read_text(encoding="utf-8")
settings = (ROOT / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
check("the setup card offers it", "ears_dialog import EarsDialog" in welcome, True)
check("…only when the machine cannot listen", "setVisible(not can_hear)" in welcome, True)
check("Settings → Voice offers it", "ears_dialog import EarsDialog" in settings, True)
spec = (ROOT / "packaging" / "arcdesk.spec").read_text(encoding="utf-8")
check("the build collects vosk, so the .exe can actually hear", '"vosk"' in spec, True)
wf = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
check("the build installs the ears one package at a time", "foreach ($pkg in" in wf, True)

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
