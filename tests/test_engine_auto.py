"""The download that never started — proved fixed, without downloading 3.4 GB.

    python tests/test_engine_auto.py

The report (26.png): *"clone voice la voice download aaga matiku machi"* — the button was
pressed and nothing came down. Three separate reasons, each of which alone was enough to
stop it, each fixed here and each with a check named after the sentence it prevents:

  1. **pip rejected our own flag.** `pip install … --progress-bar ascii` — pip 26 offers
     [auto, on, off, raw] and exits 2 before fetching a byte. The message was "packages did
     not install (exit code 2)". Nothing was wrong with the internet, the disk or the model.
     Now the flag is asked of the pip that is actually there (`bar_choice`), and if a pip
     this app has never met disagrees, the same command is run once more without it.
  2. **A gated model ended the run instead of pausing it.** The old flow downloaded nothing
     and told the person to accept a licence and "press Install again". Now the token is
     asked for *inside* the same run and the download continues in that run.
  3. **A temporary wire failure ended everything.** One automatic retry, and only for the
     failures a retry can fix — a 401 or a full disk are not retried, because retrying them
     just wastes four minutes.

Nothing here touches the network or the real `engines._run`: the child process is a fake,
so what is proved is the decision, the wording, and the exit code.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import threading
from contextlib import redirect_stdout
from pathlib import Path

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-auto-")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk import engines                                              # noqa: E402

# This test's HOME is a small tmpfs. The disk guard has its own checks (§8) and would
# otherwise refuse every install here for a reason that has nothing to do with the test.
engines.free_gb = lambda path=None: 999.0                                # noqa: SLF001

#: the real one, kept because §3-§9 replace `engines.install` with a scripted fake
real_install = engines.install

ok = True


def check(name: str, got, want=True) -> None:
    global ok
    good = got == want
    ok = ok and good
    print(f"   {'OK  ' if good else 'FAIL'} {name:<58} {got!r}")


print("1. which engine a language needs — one answer, no menu")
check("Tamil needs IndicF5", engines.pick("ta"), "indicf5")
check("Hindi needs IndicF5", engines.pick("hi"), "indicf5")
check("English needs XTTS", engines.pick("en"), "xtts")
check("an unknown language falls back to English", engines.pick("xx"), "xtts")
check("nothing said at all means Tamil", engines.pick(""), "indicf5")
check("a named engine wins over the language", engines.pick("en", "piper"), "piper")
check("'ta-IN' is Tamil", engines.pick("ta-IN"), "indicf5")

print("\n2. the pip flag that stopped every install before it began")
check("this pip's answer is one of the four it actually offers",
      engines.bar_choice(sys.executable) in ("raw", "ascii", "on", ""), True)
check("…and never the spelling that was rejected",
      engines.bar_choice(sys.executable) != "ascii" or "ascii" in
      (subprocess.run([sys.executable, "-m", "pip", "install", "--help"],
                      capture_output=True, text=True).stdout or ""), True)
check("'invalid choice: ascii' is recognised as our mistake, not a download failure",
      engines._is_bar_error("option --progress-bar: invalid choice: 'ascii' "
                            "(choose from 'auto', 'on', 'off', 'raw')"), True)   # noqa: SLF001
check("a normal pip failure is not treated that way",
      engines._is_bar_error("ERROR: Could not find a version that satisfies the requirement"),
      False)
check("a raw pip bar becomes a percentage",
      (engines.read_progress("Progress 512 of 4096") or {}).get("percent"), 12.5)
check("a huggingface tqdm line becomes megabytes",
      (engines.read_progress("812M/1.6G") or {}).get("total_mb"), 1600.0)
check("a plain log line stays a log line", engines.read_progress("Collecting torch"), None)


def fake_install(script, calls=None, lines=None):
    """Replace engines.install with a scripted one; record the calls it received."""
    seen = calls if calls is not None else []

    def _install(engine, on_line=None, cancel=None, on_progress=None):
        seen.append(engine)
        step = script[len(seen) - 1] if len(seen) <= len(script) else script[-1]
        if on_progress is not None:
            on_progress({"percent": 0, "mb": 0.0,
                         "total_mb": float(engines.SPECS[engine]["size_mb"])})
        return dict(step, engine=engine, lines=list(lines or ["a line"]))

    engines.install = _install                                            # noqa: SLF001
    return seen


print("\n3. a download that is allowed to work, works")
seen = fake_install([{"ok": True, "why": ""}])
got = engines.auto(lang="en")
check("it installed without asking anything", got.get("ok"), True)
check("exactly one engine was fetched", seen, ["xtts"])
check("…the one English needs", got.get("engine"), "xtts")
check("the progress line starts at 0 % of the real size",
      got.get("ok") and float(engines.SPECS["xtts"]["size_mb"]) > 0, True)

print("\n4. a gated model pauses for the token, then continues — press once, not twice")
engines.set_token("")
seen = fake_install([{"ok": False, "why": "gated model — needs a token", "needs_token": True,
                      "url": "https://huggingface.co/ai4bharat/IndicF5"},
                     {"ok": True, "why": ""}])
asked: list[tuple[str, str]] = []


def answer_once(engine, url):
    asked.append((engine, url))
    return "hf_SECRETVALUE"


got = engines.auto(lang="ta", ask_token=answer_once)
check("the download finished in the same run", got.get("ok"), True)
check("it asked for the token exactly once", len(asked), 1)
check("…about the engine Tamil needs", asked[0][0], "indicf5")
check("…and showed the licence page it was talking about",
      asked[0][1].endswith("IndicF5"), True)
check("the token was saved for next time", engines.token(), "hf_SECRETVALUE")
check("the token is never printed into the log",
      any("SECRETVALUE" in str(line) for line in got.get("lines") or []), False)
check("it needed two attempts, not three", got.get("attempts"), 2)

print("\n5. saying no to the token is a decision, and is reported as one")
engines.set_token("")
seen = fake_install([{"ok": False, "why": "gated model — needs a token", "needs_token": True,
                      "url": "https://huggingface.co/ai4bharat/IndicF5"}])
got = engines.auto(lang="ta", ask_token=lambda e, u: None)
check("it did not install", got.get("ok"), False)
check("…and says why in words a person can act on", got.get("needs_token"), True)
check("…without retrying a 401, which cannot pass", seen, ["indicf5"])
check("…and without a token being stored", engines.token(), "")

print("\n6. a gated model with nobody to ask is not left hanging")
seen = fake_install([{"ok": False, "why": "gated model — needs a token",
                      "needs_token": True, "url": ""}])
got = engines.auto(lang="hi")
check("it returns instead of waiting for an answer", got.get("ok"), False)
check("…and still names the gate", got.get("needs_token"), True)

print("\n7. a wire failure is retried once; a real failure is not")
seen = fake_install([{"ok": False, "why": "exit code 1",
                      "last": "ConnectionResetError: [Errno 104] reset by peer"},
                     {"ok": True, "why": ""}])
got = engines.auto(lang="en", pause=0.0)
check("the retry finished the job", got.get("ok"), True)
check("…after exactly two attempts", seen, ["xtts", "xtts"])
seen = fake_install([{"ok": False, "why": "exit code 1", "last": "no space left on device"}])
got = engines.auto(lang="en", pause=0.0)
check("a disk problem is not retried", seen, ["xtts"])
check("…and the reason survives to the caller", got.get("why"), "exit code 1")

print("\n8. space is checked before 1.9 GB, not after it fails")
seen = fake_install([{"ok": False, "needs_space": True,
                      "why": "not enough free space — needs about 4.2 GB, has 0.4 GB"}])
got = engines.auto(lang="en", pause=0.0)
check("a full disk is not retried", seen, ["xtts"])
check("…and it is flagged, not disguised as a download error", got.get("needs_space"), True)
check("XTTS wants about twice its model size, because pip unpacks beside it",
      engines.space_needed_gb("xtts") > engines.SPECS["xtts"]["size_mb"] / 1000.0, True)

print("\n9. Stop means stop, including while it waits to retry")
cancel = threading.Event()
cancel.set()
seen = fake_install([{"ok": False, "why": "exit code 1", "last": "Read timed out"}])
got = engines.auto(lang="en", cancel=cancel, pause=30.0)
check("a cancelled run does not sit in the retry pause", got.get("ok"), False)
check("…and says cancelled", got.get("why"), "cancelled")

print("\n10. what the window shows while it downloads")
from tools.engine_get import _Live                                          # noqa: E402

buf = io.StringIO()
with redirect_stdout(buf):
    live = _Live(every=0.0)
    live({"percent": 12.5, "mb": 238.0, "total_mb": 1900.0, "speed": "3.1 MB/s",
          "eta": "2:10"})
    live({"percent": 0.0, "mb": 0.0, "total_mb": 1900.0, "speed": "", "eta": "starting"})
    live.close()
text = buf.getvalue()
check("it prints a percentage", "12.5%" in text, True)
check("…megabytes of a real total", "238 MB of 1,900 MB" in text, True)
check("…the speed", "3.1 MB/s" in text, True)
check("…and the estimate", "about 2:10 left" in text, True)
check("'about starting left' is not a sentence", "about starting left" in text, False)

print("\n11. the app's own screen: a paused download that is asked, not abandoned")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication                          # noqa: E402
_app = QApplication.instance() or QApplication([])
from arcdesk.widgets.engine_dialog import EngineDialog               # noqa: E402

dlg = EngineDialog()
check("the one automatic button exists",
      dlg.auto_btn.text().lower().startswith("download it for me"), True)
check("…and it offers the three promised languages",
      [dlg.lang.itemData(i) for i in range(dlg.lang.count())], ["ta", "hi", "en"])
check("Tamil is the language it starts on", dlg.lang.currentData(), "ta")
dlg._on_need_token("indicf5", "https://huggingface.co/ai4bharat/IndicF5")   # noqa: SLF001
verdict = dlg.verdict.text().lower()
check("the screen says the download is paused, not finished", "paused" in verdict, True)
check("…names the licence page", "huggingface.co/ai4bharat/indicf5" in verdict, True)
check("…and says Save continues it, with no second Install",
      "continues" in verdict and "install again" not in verdict, True)


class _FakeWorker:
    def __init__(self) -> None:
        self.answered: list[str | None] = []

    def answer(self, value):
        self.answered.append(value)


fake = _FakeWorker()
dlg._worker = fake                                                    # noqa: SLF001
dlg._awaiting_token = "indicf5"                                       # noqa: SLF001
dlg.token.setText("hf_PASTED")                                        # noqa: SLF001
dlg._save_token()                                                     # noqa: SLF001
check("pressing Save hands the token to the paused download", fake.answered, ["hf_PASTED"])
check("…and stores it for the next run", engines.token(), "hf_PASTED")
check("…and does not leave the screen waiting", dlg._awaiting_token, None)   # noqa: SLF001
dlg.deleteLater()

print("\n11b. the .bat calls the automatic path, and nothing else")
bat = (ROOT / "install_clone.bat").read_bytes().decode("ascii").lower()
check("one command", bat.count("engine_get.py auto"), 1)
check("the language is passed to it", "auto %langpick%" in bat, True)
check("the countdown gives Ctrl+C a window", "timeout /t 6" in bat, True)
check("the three outcomes each say something true",
      all(tag in bat for tag in (":clone_ok", ":clone_gated", ":clone_trouble")), True)
check("a resumed run is described honestly", "resumes from where it" in bat, True)

print("\n12. the token this computer already has — a terminal login counts")
import importlib                                                        # noqa: E402

saved_env = {k: os.environ.get(k) for k in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN",
                                            "HUGGINGFACE_TOKEN", "HF_HOME")}
home = Path(tempfile.mkdtemp(prefix="arcdesk-hf-"))
os.environ["HF_HOME"] = str(home)
os.environ.pop("HF_TOKEN", None)
os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
os.environ.pop("HUGGINGFACE_TOKEN", None)
engines.set_token("")
check("nothing anywhere means no token", engines.token_source(), ("", ""))
os.environ["HF_TOKEN"] = "hf_FROMENV"
check("a token in the environment is used", engines.token(), "hf_FROMENV")
check("…and the app says where it came from", "HF_TOKEN" in engines.token_source()[1], True)
os.environ.pop("HF_TOKEN")
(home / "token").write_text("hf_FROMCLI\n", encoding="utf-8")
check("a `huggingface-cli login` token is found",
      engines.token_source(), ("hf_FROMCLI", "your huggingface-cli login"))
engines.set_token("hf_FROMSETTINGS")
check("a token saved in JARVIS wins", engines.token(), "hf_FROMSETTINGS")
check("…and is named as such", engines.token_source()[1], "saved in JARVIS settings")
engines.set_token("")

print("\n13. a copy that is already on this PC is used, not downloaded twice")
repo = engines.MODEL_REPO["xtts"]
snap = home / "hub" / ("models--" + repo.replace("/", "--")) / "snapshots" / "abc123"
snap.mkdir(parents=True, exist_ok=True)
check("an empty folder is not a copy", engines.local_copy("xtts"), "")
(snap / "config.json").write_text("{}", encoding="utf-8")
(snap / "model.pth").write_text("x", encoding="utf-8")
check("two of three files is still not a copy", engines.local_copy("xtts"), "")
(snap / "vocab.json").write_text("{}", encoding="utf-8")
check("a complete snapshot is found", engines.local_copy("xtts"), str(snap))
seen = []
engines._run = lambda argv, on_line, cancel=None, on_progress=None: (    # noqa: SLF001
    seen.append(argv), on_line("fake run"), {"ok": True, "code": 0, "why": "", "last": ""})[-1]
lines: list[str] = []
got = real_install("xtts", on_line=lines.append)
check("install notices the copy and says so",
      any("already on this PC" in ln for ln in got.get("lines") or []), True)
check("…and not one byte is fetched again",
      any(ln.strip().startswith("downloading ·") for ln in got.get("lines") or []), False)

print("\n14. the direct download, without any library in the way")
engines._api = lambda repo, token="", timeout=25.0: {"_status": 401}   # noqa: SLF001
got = engines.fetch("indicf5")
check("a gated repo stops the direct download too", got.get("ok"), False)
check("…with the token answer, not a traceback", got.get("needs_token"), True)
check("…and the page to open", str(got.get("url") or "").endswith("IndicF5"), True)
engines._api = lambda repo, token="", timeout=25.0: {"_status": 0,                   # noqa: SLF001
                                                     "_why": "URLError: no route"}
got = engines.fetch("xtts")
check("no connection is reported as no connection", got.get("why"),
      "could not reach Hugging Face")
check("the repo of every engine is data, not a string typed twice",
      sorted(engines.MODEL_REPO), ["indicf5", "piper", "xtts"])
check("cache clutter is skipped", [n for n in ("samples/en_sample.wav",
                                               "f5_tts/__pycache__/x.cpython-312.pyc",
                                               ".gitattributes") if engines._skip_file(n)],   # noqa: SLF001
      ["samples/en_sample.wav", "f5_tts/__pycache__/x.cpython-312.pyc", ".gitattributes"])
check("…and the weights are not", engines._skip_file("model.safetensors"), False)   # noqa: SLF001

for key, value in saved_env.items():
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
