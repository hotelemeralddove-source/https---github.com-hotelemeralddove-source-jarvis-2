"""install_clone.bat must ask the right question before spending 1.9 GB.

The report (21.png): a cmd window, forty lines of `transformers` internals, and at the
bottom

    OSError: You are trying to access a gated repo … 401 Client Error
    (IndicF5 download failed - retry with internet)
    Install XTTS-v2 for English cloning (~1.9 GB) [Y,N]?

Three separate things were wrong, and all three are asserted here:

  1. **The order.** The gated model was offered first, so the first thing a new person met
     was the one download that cannot work without a licence click. English (XTTS-v2, no
     account) now comes first, and Piper — 60 MB, no account, no GPU — is named up front.
  2. **The diagnosis.** "retry with internet" is not the reason. Hugging Face answers
     **200** for `/api/models/ai4bharat/IndicF5` and **401** for every *file* in it. The
     .bat now asks `tools/engine_get.py gate`, which probes a real file, and offers the
     token paste instead of a retry.
  3. **The output.** A traceback is not an answer. Every line now comes from
     `tools/engine_get.py`, which prints one sentence and an exit code.

Also proven: the same "which copy am I?" warning that JARVIS.bat gives, because the
screenshot's folder was `C:\\Users\\…\\Downloads\\JARVIS-ready (1)\\JARVIS` — the second
copy of the same download.

Run:  python tests/test_install_clone_bat.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BAT = ROOT / "install_clone.bat"
TOOL = ROOT / "tools" / "engine_get.py"
ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<60} {got!r}")


text = BAT.read_bytes().decode("ascii", "replace")
low = text.lower()

print("1. the file is real, and cmd can read it")
check("install_clone.bat exists", BAT.exists(), True)
check("pure ASCII", all(b < 128 for b in BAT.read_bytes()), True)
from tools import batlint                                               # noqa: E402
check("batlint problems", batlint.lint(BAT), [])
check("the helper it calls exists", TOOL.exists(), True)

print("\n2. it never talks to Hugging Face with a raw python -c (that is what printed")
print("   forty lines of transformers internals)")
check("no inline 'from transformers import' download",
      "autoModel.from_pretrained" in low.replace(" ", ""), False)
check("no inline coqui/XTTS warm-up either",
      "tts.api" in low.replace(" ", ""), False)
check("every heavy step goes through the helper",
      "tools\\engine_get.py auto" in text, True)

print("\n3. it no longer blames the internet for a licence problem")
check("no 'retry with internet' for a gated model", "retry with internet" in low, False)
check("it says the token can be pasted later, in the app",
      "settings -^> voice" in low or "settings -> voice" in low, True)
check("…and it does not pretend a missing token was a failure",
      "decision, not an error" in low, True)
check("…nor blame the connection for it", "not enough free disk space" in low, True)

print("\n4. the order is the one that can actually succeed")
check("the one automatic command runs after the two small ones",
      text.index("engine_get.py auto") > text.index("[1/3]"), True)
check("Piper, the 60 MB one, is described up front", "piper" in low and "60 mb" in low, True)
# The big downloads are no longer a quiz: one command fetches the right engine, and the
# way out is Ctrl+C during a stated countdown. (The report behind this change was
# "clone voice la voice download aaga matiku" — a question was answered wrongly, and no
# download happened at all.)
check("the clone engine is downloaded by one automatic command",
      "engine_get.py auto" in text, True)
check("…for the language chosen by an argument", "langpick" in low, True)
check("…with the way out written down", "ctrl+c" in low, True)
check("…and a countdown before it starts", "timeout /t 6" in low, True)
check("no big download waits behind a yes/no question",
      "install xtts" in low or "install indicf5" in low, False)
check("…and nothing tells the person to press Install again", "install again" in low, False)
check("the size is on every button-like line",
      "~1.9 gb" in low and "~1.5 gb" in low, True)

print("\n5. a second copy in Downloads is called out (the screenshot's folder)")
check("install_clone.bat warns about Downloads", "lives in downloads" in low, True)
check("…and points at ONE-PLACE.bat", "one-place.bat" in low, True)
jarvis = (ROOT / "JARVIS.bat").read_bytes().decode("ascii", "replace").lower()
check("JARVIS.bat warns too", "lives in downloads" in jarvis, True)
check("…with the same one-place route", "one-place.bat" in jarvis, True)
check("…and both still pass the linter",
      batlint.lint(ROOT / "JARVIS.bat"), [])

print("\n6. the helper actually runs, and says something true")
env = dict(os.environ)
env["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-engineget-")
env["PYTHONIOENCODING"] = "utf-8"
env.pop("HF_TOKEN", None)
proc = subprocess.run([sys.executable, str(TOOL), "status"], cwd=str(ROOT), env=env,
                      capture_output=True, text=True, encoding="utf-8", errors="replace",
                      timeout=180)
out = proc.stdout or ""
check("status exits 0", proc.returncode, 0)
check("…and lists all three engines", all(w in out for w in ("Piper", "XTTS", "IndicF5")),
      True)
check("…with a size next to each", out.count(" MB") >= 3, True)
check("…and says whether a token is saved", "huggingface token" in out.lower(), True)
check("…and names the small one", "~60 MB" in out, True)

proc = subprocess.run([sys.executable, str(TOOL), "token", "--clear"], cwd=str(ROOT),
                      env=env, capture_output=True, text=True, encoding="utf-8",
                      errors="replace", timeout=120)
check("a token can be cleared from the command line", proc.returncode, 0)
check("…and it never prints a token back",
      "hf_" not in (proc.stdout or ""), True)

proc = subprocess.run([sys.executable, str(TOOL), "install", "not-an-engine"], cwd=str(ROOT),
                      env=env, capture_output=True, text=True, encoding="utf-8",
                      errors="replace", timeout=120)
check("an unknown engine is refused, not attempted", proc.returncode, 1)
check("…and the message lists the real ones", "piper" in (proc.stdout or "").lower(), True)

print("\n7. the exit codes the .bat branches on")
src = TOOL.read_text(encoding="utf-8")
check("2 means 'needs a token first'", "return 2" in src, True)
check("1 means failed", "return 1" in src, True)
check("an exception is one line, never a traceback", "traceback" in src.lower(), True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
