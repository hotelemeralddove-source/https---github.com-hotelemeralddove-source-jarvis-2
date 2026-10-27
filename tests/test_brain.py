"""A brain in the box, and the name it says out loud

    python tests/test_brain.py

Two requests, one file:

  * *"no local model detected nu varuthu, brain ah add pana solluthu — athayum oru
    bundle ah koduthudu"* → a model that installs and starts from inside the app;
  * *"athu pesum pothu 'I am ARC' nu soluthu; 'I am JARVIS' nu sonna semaya irukkum"* →
    the spoken identity is JARVIS, from one setting.

The download is 1.1 GB, so the network calls and the child processes are faked here. The
logic, the wording, the config it writes and the dialog are real.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-brain-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])

from arcdesk import brain, config, identity  # noqa: E402
from arcdesk.ai import persona  # noqa: E402
from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets.brain_dialog import BrainDialog  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:46]!r}")
    ok &= bool(good)


print("1) the name it says is JARVIS, and it is one setting")
cfg = config.load()
check("the default name is JARVIS", identity.name(cfg), "JARVIS")
check("the persona prompts it by name", "You are JARVIS" in persona.system_prompt(cfg), True)
check("…and forbids the other one", 'never "I am ARC"' in persona.system_prompt(cfg), True)
check("the intro is what a person asked for", identity.intro(cfg),
      "I am JARVIS, and this is my voice on your machine.")
check("Lite introduces itself the same way",
      "I am JARVIS" in __import__("arcdesk.ai.lite", fromlist=["lite"]).respond(
          "who are you")[0], True)
cfg["ai"]["name"] = "FRIDAY"
check("a different name is used everywhere at once", identity.name(cfg), "FRIDAY")
check("…including the prompt", "You are FRIDAY" in persona.system_prompt(cfg), True)
check("an empty name falls back, never blank", identity.name({"ai": {"name": "  "}}),
      "JARVIS")

print("\n2) two models, with their real sizes and an honest label")
st = brain.status()
check("two options", len(st["models"]), 2)
check("the small one can drive the tools", st["models"]["small"]["tools"], True)
check("the tiny one is labelled chat-only", st["models"]["tiny"]["tools"], False)
check("sizes are stated", (st["models"]["small"]["mb"], st["models"]["tiny"]["mb"]),
      (1066, 469))
check("nothing downloaded yet", st["installed"], [])
check("and the sentence offers the fix", "press Install" in st["sentence"], True)

print("\n3) install: packages, then weights, then a server that really answers")
CALLS: list[list[str]] = []


def fake_run(argv, on_line, cancel=None):
    CALLS.append(list(argv))
    on_line("fake: " + " ".join(argv[1:3]))
    return {"ok": True, "code": 0, "why": "", "last": ""}


real_run = brain.__dict__["ensure_packages"]
import arcdesk.engines as engines_mod  # noqa: E402
engines_mod._run = fake_run            # the seam the brain uses

DOWNLOADS: list[str] = []
brain.MIN_MODEL_BYTES = 1024        # keep the fake small: a test must not fill a disk


def fake_download(key=brain.DEFAULT_MODEL, on_line=None, cancel=None):
    DOWNLOADS.append(key)
    p = brain.gguf_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\0" * 4096)                   # big enough to count as present
    if on_line:
        on_line("  saved (fake)")
    return {"ok": True, "path": str(p), "why": ""}


brain.download = fake_download
check("packages install first", brain.ensure_packages(lambda _l: None)["ok"], True)
check("…with pip, from the app's own python",
      CALLS and "pip" in CALLS[0] and "llama-cpp-python[server]" in " ".join(CALLS[0]), True)
check("the model is fetched once", brain.download("small")["ok"], True)
check("now it counts as installed", brain.model_present("small"), True)
check("only the one that was downloaded", brain.installed_models(), ["small"])

print("\n4) the server: started, waited for, and pointed at the app")
TRUE_PORT_OPEN = brain._port_open        # the real one, saved before any faking
brain._port_open = lambda port=brain.PORT, timeout=0.25: True   # pretend it answered


class FakeProc:
    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass

    stderr = None


class FakePopen:
    def __init__(self, *a, **kw):
        self.args = a[0] if a else kw.get("args")

    def __call__(self, argv, **kw):
        return FakeProc()


real_popen = brain.subprocess.Popen
brain.subprocess.Popen = FakePopen()
res = brain.start_server("small", on_line=lambda _l: None, wait=5)
check("it started", res["ok"], True)
check("it binds to localhost only", res["url"].startswith("http://127.0.0.1"), True)
check("and the port is ours, not 8080", res["url"].endswith(f":{brain.PORT}/v1"), True)
brain.subprocess.Popen = real_popen

cfg = config.load()
brain.apply_config(cfg, "small")
ai = cfg["ai"]
check("the app is pointed at it", ai["base_url"].endswith("/v1"), True)
check("provider is the generic local one", ai["provider"], "custom")
check("and the brain is enabled", ai["enabled"], True)
saved = config.load()
check("it was saved, not just held in memory",
      str(saved["ai"].get("base_url", "")).endswith(f":{brain.PORT}/v1"), True)

print("\n5) a build with no Python says so instead of hanging")
sys.frozen = True
real_external = engines_mod.external_python
brain._port_open = lambda port=brain.PORT, timeout=0.25: False   # nothing is answering
engines_mod.external_python = lambda: ""
engines_mod.sidecar_python = lambda: Path("/nonexistent/python")
py, why = brain._env_python()
check("no interpreter", py, "")
check("…and one sentence that says what to do", "python.org" in why, True)
check("starting refuses honestly",
      brain.start_server("small", wait=1)["ok"], False)
del sys.frozen
engines_mod.external_python = real_external
brain._port_open = TRUE_PORT_OPEN
brain._SERVER = None                   # forget the fake process from section 4

print("\n6) the dialog: sizes on the button, real verdicts, and it ends configured")
cfg = config.load()
dlg = BrainDialog(cfg, get_theme("chill"))
check("both models in the picker", dlg.picker.count(), 2)
dlg.picker.setCurrentIndex(1)          # the tiny model: still not downloaded
check("the button carries the download size", "469 MB" in dlg.go.text(), True)
dlg.picker.setCurrentIndex(0)
check("a downloaded model offers Start instead", "Start" in dlg.go.text(), True)
check("the download is described before it starts",
      "1.5 GB of RAM" in dlg.detail.text(), True)
dlg._finished({"ok": True, "why": ""})
check("success says it is running and used", "running on this laptop" in dlg.verdict.text(),
      True)
dlg._finished({"ok": False, "why": "cancelled"})
check("a cancel says stopped", dlg.verdict.text().startswith("Stopped"), True)
dlg._finished({"ok": False, "why": "exit code 1"})
check("a failure keeps Lite alive in the sentence", "Lite keeps working" in dlg.verdict.text(),
      True)

print("\n7) it is reachable from where the complaint happened")
welcome = (ROOT / "arcdesk" / "widgets" / "welcome.py").read_text(encoding="utf-8")
settings = (ROOT / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
check("the setup card offers it on the brain step", "brain_dialog import BrainDialog" in welcome,
      True)
check("Settings → Local AI offers it", "brain_dialog import BrainDialog" in settings, True)
check("the setup card no longer just says 'later in Settings'",
      "Add a brain" in welcome, True)
check("the name is editable in Settings", "ai_name" in settings, True)

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
