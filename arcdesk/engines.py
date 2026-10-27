"""The neural engines that make a cloned voice sound like a person.

A clone is not a setting — it is a model. Without one of these, ARC can only speak in the
system voice, and it must say so. This module owns the whole "get the model" job so the
app can do it in one click instead of sending anyone to a command prompt:

    status()   -> what is installed, what is missing, how big, and why
    install()  -> pip install + a warm-up download, streaming every line it prints
    method()   -> how this build can install anything (pip / bundled script / no)

Rules this file keeps, because a wrong "ready" is worse than a slow one:

* nothing is called ready until the *model weights* are on disk, not just the package;
* every failure carries the last real error line, not "something went wrong";
* a cancelled install is reported as cancelled — never as installed;
* every size is stated before the download starts (~1.5 GB, ~1.9 GB).
"""
from __future__ import annotations

import os
import subprocess

from . import quiet
import sys
import threading
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]

#: The voice that needs no download at all, listed first because it is the easy answer.
EASY = "windows"

# The Piper download: one small neural voice file per language. 60 MB instead of 1.5 GB,
# no torch, and it runs on a CPU fast enough to answer a question. Written as a program
# because it is handed to a child interpreter and prints its own progress bars.
_PIPER_WARM = r"""
import os, sys, urllib.request
sys.path.insert(0, os.getcwd())
from arcdesk.ai.voice import piper_dirs

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
# (path on the hub, filename kept locally). Small first: English, then Hindi, then Tamil.
VOICES = [
    ("en/en_GB/alan/medium/en_GB-alan-medium.onnx", "en_GB-alan-medium.onnx"),
    ("en/en_GB/alan/medium/en_GB-alan-medium.onnx.json", "en_GB-alan-medium.onnx.json"),
    ("en/en_US/ryan/high/en_US-ryan-high.onnx", "en_US-ryan-high.onnx"),
    ("en/en_US/ryan/high/en_US-ryan-high.onnx.json", "en_US-ryan-high.onnx.json"),
    ("hi/hi_IN/pratham/medium/hi_IN-pratham-medium.onnx", "hi_IN-pratham-medium.onnx"),
    ("hi/hi_IN/pratham/medium/hi_IN-pratham-medium.onnx.json", "hi_IN-pratham-medium.onnx.json"),
]
target = piper_dirs()[0]
target.mkdir(parents=True, exist_ok=True)
got = 0
for rel, name in VOICES:
    out = target / name
    if out.exists() and out.stat().st_size > 1024:
        got += 1
        print("already here: " + name)
        continue
    url = BASE + "/" + rel
    part = out.with_name(out.name + ".part")     # a Path, never Path + str
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    sys.stdout.write("  %6.1f/%6.1f MB %s\r" % (done / 1e6, total / 1e6, name))
                    sys.stdout.flush()
        if total and part.stat().st_size != total:
            part.unlink()
            raise IOError("arrived " + str(part.stat().st_size) + " of " + str(total) + " bytes")
        part.replace(out)
        got += 1
        print("downloaded: " + name)
    except Exception as exc:
        try:
            if part.exists():
                part.unlink()
        except OSError:
            pass
        print("skipped " + name + " (" + type(exc).__name__ + ": " + str(exc)[:120] + ")")
if got == 0:
    raise SystemExit("no voice could be downloaded")
print("piper voices ready: " + str(got) + " files")
"""

#: engine id -> what it is for, how big, and what makes it real.
#: Order matters: the dialog lists them smallest-first, so the easy answer is on top.
SPECS: dict[str, dict] = {
    "piper": {
        "label": "Piper",
        "langs": "English, Hindi",
        "size_mb": 60,
        "packages": ["piper-tts"],
        "warm": _PIPER_WARM,
        "why": "a small neural voice that runs on any laptop — no GPU, no torch, "
               "downloads in a minute",
        "needs": "about 60 MB per language voice",
        "easy": True,
    },
    "indicf5": {
        "label": "IndicF5",
        "langs": "Tamil, Hindi",
        "size_mb": 1500,
        "packages": ["torch", "transformers", "soundfile"],
        "warm": ("from transformers import AutoModel\n"
                 "AutoModel.from_pretrained('ai4bharat/IndicF5', trust_remote_code=True)\n"),
        "why": "the only one of the two that can speak Tamil or Hindi in a cloned voice",
        "needs": "a GPU to feel instant; on a CPU it works but slowly",
        "easy": False,
    },
    "xtts": {
        "label": "XTTS-v2",
        "langs": "English",
        "size_mb": 1900,
        "packages": ["coqui-tts"],
        "warm": ("from TTS.api import TTS\n"
                 "TTS('tts_models/multilingual/multi-dataset/xtts_v2')\n"),
        "why": "cloned English; it cannot speak Tamil",
        "needs": "works on a CPU, slower than real time on a weak laptop",
        "easy": False,
    },
}

#: torch from PyPI on Windows is a ~2.5 GB CUDA build. Most laptops have no NVIDIA GPU at
#: all, and a 2.5 GB download over a home connection is what "downloading but never
#: downloading" looked like. The CPU build is ~200 MB from its own index.
_TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def split_packages(packages: list[str]) -> tuple[list[str], list[str]]:
    """(packages that need the CPU-only torch index, the rest).

    Kept as a function so the test can prove the split without downloading anything.
    """
    heavy = [p for p in packages if p.split("==")[0].split("[")[0].strip().lower() == "torch"]
    rest = [p for p in packages if p not in heavy]
    return heavy, rest


Line = Callable[[str], None]
Progress = Callable[[dict], None]



# ---------------------------------------------------------------- gated models
# IndicF5 is not simply "on huggingface" — AI4Bharat publishes it behind a licence.
# Without a token, Hugging Face answers 401 for every file, forever: the app looks like it
# is downloading and never is. That is exactly the report:
#   "OSError: You are trying to access a gated repo ... 401 Client Error"
# So the gate is checked FIRST, before 200 MB of torch, and the answer says what to do.
#: Where each engine's weights live. One table, used by the licence gate, by the direct
#: download and by "is it already on this PC" — three questions, one answer.
MODEL_REPO = {
    "indicf5": "ai4bharat/IndicF5",
    "xtts": "coqui/XTTS-v2",
    "piper": "rhasspy/piper-voices",
}

#: Repos whose FILES need a token. Measured 2026-10-25: IndicF5 answers 401 on a file
#: and `gated: auto` in its metadata, which means any logged-in token is enough — there
#: is no manual approval to wait for. XTTS-v2 is public. That is why "it downloads fine
#: in my terminal" and "the app asks me for a licence" can both be true at once.
HF_GATED = {"indicf5": MODEL_REPO["indicf5"]}

#: The files that make an engine usable. Used to answer "is a copy already here?" and
#: "what does a direct download have to fetch?".
ESSENTIAL = {
    "indicf5": ("config.json", "model.safetensors"),
    "xtts": ("config.json", "model.pth", "vocab.json"),
    "piper": (".onnx.json",),
}


def _http_status(url: str, token: str = "", timeout: float = 12.0) -> int:
    """Status code for one URL; 0 when it cannot be reached. One seam, so tests are fast."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "arcdesk"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(getattr(r, "status", 200))
    except urllib.error.HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0)
    except Exception:                                            # noqa: BLE001
        return 0


def hf_home() -> Path:
    """Where Hugging Face keeps its cache and its token on this computer."""
    import os as _os
    for name in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE"):
        value = _os.environ.get(name)
        if value:
            base = Path(value)
            return base.parent if base.name == "hub" else base
    return Path(_os.environ.get("USERPROFILE") or Path.home()) / ".cache" / "huggingface"


def token_source() -> tuple[str, str]:
    """(token, where it came from). Someone who downloaded the model in a terminal
    already has a token, and asking them to make a second one is exactly the needless
    step that makes a working download look broken.

    Order: this app's setting, then the environment, then `huggingface-cli login` —
    read through the library when it is installed, else straight from the token file,
    because that last one is the credential a terminal user already has.
    """
    import os as _os
    try:
        from . import config
        saved = str((config.load().get("engines") or {}).get("hf_token") or "").strip()
        if saved:
            return saved, "saved in JARVIS settings"
    except Exception:                                            # noqa: BLE001
        pass
    for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        value = (_os.environ.get(name) or "").strip()
        if value:
            return value, f"the {name} in your terminal"
    # The token file below is exactly what `huggingface_hub.get_token()` reads, so this
    # needs no import and no extra dependency: JARVIS must work before anything of
    # Hugging Face's is installed, which is the state a fresh laptop is in.
    for path in (hf_home() / "token", hf_home() / ".token"):
        try:
            if path.is_file():
                got = path.read_text(encoding="utf-8").strip()
                if got:
                    return got, "your huggingface-cli login"
        except Exception:                                        # noqa: BLE001
            continue
    return "", ""


def token() -> str:
    """The Hugging Face token this computer already has, if any. Never printed back."""
    return token_source()[0]


def set_token(value: str) -> None:
    """Remember (or clear) the token. Never printed back, never logged."""
    from . import config
    cfg = config.load()
    cfg.setdefault("engines", {})["hf_token"] = (value or "").strip()
    config.save(cfg)


#: The file the gate is measured on. **Not** `/api/models/<repo>`.
#:
#: Measured on 2026-10-25, from the report in `21.png`:
#:
#:     /api/models/ai4bharat/IndicF5                 -> 200   (metadata is public)
#:     /ai4bharat/IndicF5/resolve/main/config.json   -> 401   (the FILE is gated)
#:
#: The old check therefore said "no licence needed", spent 200 MB of torch, and then died
#: on the first file with `OSError: You are trying to access a gated repo … 401`. Exactly
#: the traceback in the screenshot. A gated repo gates its files, so the file is what this
#: asks about.
GATE_PROBE_FILE = "config.json"


def gate_url(repo: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{GATE_PROBE_FILE}"


def gate(engine: str) -> dict:
    """Is this engine's model readable without a token? Measured on a real file."""
    repo = HF_GATED.get(engine)
    if not repo:
        return {"ok": True, "gated": False, "repo": ""}
    # A test or an air-gapped run can say "do not ask the network"; the answer is then
    # "unknown", which never blocks a download that might work.
    if os.environ.get("ARCDESK_OFFLINE"):
        return {"ok": True, "gated": False, "repo": repo, "unknown": True, "status": 0}
    status = _http_status(gate_url(repo), token())
    if status == 200:
        return {"ok": True, "gated": False, "repo": repo, "status": status}
    if status in (401, 403):
        return {"ok": False, "gated": True, "repo": repo, "status": status,
                "url": f"https://huggingface.co/{repo}"}
    if status == 404:
        # the repo answers but that file name is not in it: it cannot be gated, and a
        # different file name must not be mistaken for a licence problem
        return {"ok": True, "gated": False, "repo": repo, "status": status}
    # Offline, or the API said something else: do not block a download that might work.
    return {"ok": True, "gated": False, "repo": repo, "status": status, "unknown": True}


def gate_advice(engine: str) -> str:
    """The sentence a person needs, with the two clicks that fix it."""
    repo = HF_GATED.get(engine, "the model")
    return ("Hugging Face refuses this model without a licence acceptance "
            f"(401). It is not a download problem and it will never finish on its own.\n"
            f"  1. open https://huggingface.co/{repo} and click Agree / Request access "
            f"(a free account; the licence is non-commercial)\n"
            "  2. make a token at https://huggingface.co/settings/tokens (type: read)\n"
            "  3. paste it in this window and press Save, then Install again\n"
            "  In a hurry? Piper is ~60 MB, needs no account, and speaks English and "
            "Hindi; the Windows voice needs no download at all.")


# --------------------------------------------------------------- reading progress
# pip and huggingface both print progress bars, and both write them with carriage
# returns instead of newlines. Swallowing that output is why the dialog could honestly
# say "installing…" for eleven minutes without moving: the person could not tell a
# 1.5 GB download from a hang. These patterns turn those bars into numbers.
import re as _re

_MB = {"B": 1e-6, "KB": 1e-3, "MB": 1.0, "GB": 1000.0, "TB": 1e6,
       "KIB": 0.001024, "MIB": 1.048576, "GIB": 1073.741824, "B/S": 1e-6}

_STEP = _re.compile(r"([\d.]+)\s*/\s*([\d.]+)\s*(KB|MB|GB|TB|KiB|MiB|GiB)",
                    _re.IGNORECASE)
# tqdm (huggingface) writes the unit once: "812M/1.6G"
_STEP_SHORT = _re.compile(r"(?<![\d.])([\d.]+)([KMG])/([\d.]+)([KMG])(?![\w])")
_PCT = _re.compile(r"\b(\d{1,3}(?:\.\d+)?)%")
_SPEED = _re.compile(r"([\d.]+)\s*(B|KB|MB|GB|KiB|MiB|GiB)/s", _re.IGNORECASE)
_ETA = _re.compile(r"(?:eta|<)\s*(\d+:\d{2}(?::\d{2})?)")
# `--progress-bar raw` — the spelling current pip uses when it is not drawing a bar:
# "Progress 1024 of 4096". No percentage, no unit, so it needs its own pattern or a
# modern pip would look silent for the whole download.
_RAW = _re.compile(r"Progress\s+(\d+)\s+of\s+(\d+)", _re.IGNORECASE)


def read_progress(line: str) -> dict | None:
    """Turn one line of pip/HF output into {percent, mb, total_mb, speed, eta}.

    Returns None when the line is not a progress bar, so callers can keep it as a log
    line instead of grinding it into a number.
    """
    if not line:
        return None
    text = line.replace(",", "")
    step = _STEP.search(text)
    short = None if step else _STEP_SHORT.search(text)
    pct = _PCT.search(text)
    speed = _SPEED.search(text)
    eta = _ETA.search(text)
    raw = _RAW.search(text)
    if not (step or short or pct or speed or raw):
        return None
    out: dict = {}
    if pct:
        try:
            out["percent"] = max(0.0, min(100.0, float(pct.group(1))))
        except ValueError:
            pass
    if raw:
        try:
            done_n, total_n = float(raw.group(1)), float(raw.group(2))
        except ValueError:
            done_n = total_n = 0.0
        if total_n > 0:
            out.setdefault("percent", max(0.0, min(100.0, done_n / total_n * 100.0)))
    if short:
        scale = {"K": 0.001, "M": 1.0, "G": 1000.0}
        done = float(short.group(1)) * scale[short.group(2)]
        total = float(short.group(3)) * scale[short.group(4)]
        if total > 0:
            out["mb"] = round(done, 1)
            out["total_mb"] = round(total, 1)
            out.setdefault("percent", max(0.0, min(100.0, done / total * 100.0)))
    if step:
        unit = step.group(3).upper()
        scale = _MB.get(unit, 1.0)
        try:
            done, total = float(step.group(1)) * scale, float(step.group(2)) * scale
        except ValueError:
            done = total = 0.0
        if total > 0:
            out["mb"] = round(done, 1)
            out["total_mb"] = round(total, 1)
            out.setdefault("percent", max(0.0, min(100.0, done / total * 100.0)))
    if speed:
        out["speed"] = f"{speed.group(1)} {speed.group(2).upper()}/s"
    if eta:
        out["eta"] = eta.group(1)
    out["line"] = line.strip()[:160]
    return out


# --------------------------------------------------------------------------- method
def method() -> dict:
    """How can THIS build install anything?

    A frozen one-file build has no `pip` of its own — `sys.executable` is `ArcDesk.exe`.
    Rather than pretend, the app says which of the two honest routes exists here.
    """
    frozen = bool(getattr(sys, "frozen", False))
    bat = ROOT / "install_clone.bat"
    pip_ok = False
    try:
        import importlib.util
        pip_ok = importlib.util.find_spec("pip") is not None
    except Exception:
        pip_ok = False
    can = (not frozen) and pip_ok
    if can:
        why = ""
    elif frozen and external_python():
        # one click still: the app borrows that Python and builds its own environment
        why = ""            # nothing to explain, it can install
        can = True
    elif frozen:
        why = ("this is the installed app and no Python is installed on this computer. "
               "The clone engine needs one: install Python 3 from python.org (one "
               "installer, default options), then press Install again — or use the free "
               "piper voice, which needs nothing")
    elif not pip_ok:
        why = "pip is not available to this Python"
    else:
        why = "unknown"
    return {"frozen": frozen, "pip": pip_ok, "can_install": can, "bat": str(bat),
            "bat_exists": bat.exists(), "why": why,
            "sidecar": sidecar_any(), "env": str(sidecar_dir())}


# --------------------------------------------------------------------------- status
def status() -> dict[str, dict]:
    """Per engine: ready or not, and the size it would cost to fix that."""
    from . import clone
    have = clone.engines()
    out: dict[str, dict] = {}
    for key, spec in SPECS.items():
        got = have.get(key, {})
        out[key] = {
            "id": key,
            "label": spec["label"],
            "langs": spec["langs"],
            "size_mb": spec["size_mb"],
            "why": spec["why"],
            "needs": spec["needs"],
            "ready": bool(got.get("available")),
            # ready = it can speak right now. `code` = the packages are on this PC
            # somewhere, `local` = the weights are here. Both true is ready; one of them
            # alone is a *different* sentence and a different button, which is the whole
            # difference between "kanom" and a working install.
            "code": bool(got.get("code")),
            "python": got.get("foreign", ""),
            "voices": int(got.get("voices") or 0),
            "problem": got.get("why", ""),
            "model": got.get("model", ""),
            # the same cache a terminal download fills: if it is here, nothing is fetched
            "local": local_copy(key),
            "token_from": token_source()[1],
        }
    return out


def any_ready() -> bool:
    return any(v["ready"] for v in status().values())


def line_for_voice() -> str:
    """One honest sentence for anywhere in the app that shows the reply voice."""
    st = status()
    ready = [v["label"] for v in st.values() if v["ready"]]
    if ready:
        return f"clone engine ready: {' / '.join(ready)}"
    return ("no clone engine installed yet — until one is, replies use the system voice "
            "(Settings → Voice → Get the reply-voice engine…)")


# --------------------------------------------------------------------------- install
# --------------------------------------------------------------- the .exe's sidecar
# A frozen build CANNOT import a package that is installed later: torch is not inside
# ArcDesk.exe and never will be (it would add ~2 GB to the installer). So the installed
# app gets the engine a different way: a private, disposable Python environment in the
# user's data folder, created and filled by the app itself with one click. The app then
# hands the sentence to that interpreter and plays the wav it returns. From the person's
# side it is still one button; nothing is installed globally and nothing is on PATH.
def _app_dir() -> Path:
    """Where the app's own files are — the frozen folder, or the repo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT


def external_python() -> str:
    """A Python already on this computer that we may borrow ('' if none).

    Preferred: the `py` launcher, because on Windows it always finds a real interpreter
    even when `python` is a Microsoft Store stub that opens the Store.
    """
    import shutil
    for name, probe in (("py", ["py", "-3", "-c", "print(1)"]),
                        ("python", ["python", "-c", "print(1)"]),
                        ("python3", ["python3", "-c", "print(1)"])):
        found = shutil.which(name)
        if not found:
            continue
        try:
            got = quiet.run(probe, capture_output=True, text=True, timeout=25)
        except Exception:
            continue
        if got.returncode == 0 and "1" in (got.stdout or ""):
            return found if name != "py" else found      # 'py' is run with -3 below
    return ""


def sidecar_dir() -> Path:
    from .config import data_dir
    return data_dir() / "engine_env"



# ------------------------------------------------------- use what you installed
# The report: "manual ah nan voice clone applications through terminal la download
# paniten but jarvis kula again install pana solluthu". Of course it does: the person
# ran `pip install torch transformers` in a terminal, which means SOME python on the PC
# has them — but the app runs in its own .venv, and a different interpreter's packages are
# invisible from there. Telling them to install a second copy of a 1.5 GB engine is not an
# answer, so the app now LOOKS for the python that already has it and hands it the job.
_ENGINE_MODULES = {"indicf5": ("transformers", "torch"), "xtts": ("TTS", "torch"),
                   "piper": ("piper",)}


def interpreters() -> list[tuple[str, str]]:
    """Every python on this machine worth asking, most likely first: (label, path)."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, path: str | Path) -> None:
        try:
            text = str(path)
        except Exception:                                        # noqa: BLE001
            return
        if not text or text in seen:
            return
        seen.add(text)
        found.append((label, text))

    add("this app", sys.executable)
    app = _app_dir()
    for cand in (app / ".venv" / "Scripts" / "python.exe", app / ".venv" / "bin" / "python",
                 ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if cand.exists():
            add("the app's .venv", cand)
    if sidecar_python().exists():
        add("the engine folder", sidecar_python())
    # A conda environment is how most people who use a terminal install this
    # (`conda create -n indicf5 python=3.10` then `pip install …`). Before fix52 it was
    # invisible to JARVIS, so the app said "not installed" to somebody who had just
    # installed it — the exact complaint this project keeps answering.
    pointed = (os.environ.get("ARCDESK_ENGINE_PYTHON") or "").strip()
    if pointed and Path(pointed).is_file():
        add("the python you pointed at", pointed)      # an explicit choice wins, first
    for label, path in conda_pythons():
        add(label, path)
    ext = external_python()
    if ext:
        add("python on PATH", ext)
    return found


def conda_pythons() -> list[tuple[str, str]]:
    """Every conda environment on this PC, as (label, python path), newest name first.

    Conda keeps envs in a handful of well-known places. All of them are cheap to list, and
    a wrong guess costs nothing: each candidate is probed for the engine's packages before
    it is offered to the person, so an empty env can never be mistaken for a working one.
    """
    import os as _os
    home = Path(_os.environ.get("USERPROFILE") or Path.home())
    roots: list[Path] = []
    for value in (_os.environ.get("CONDA_ENVS_PATH") or "").replace(";", ":").split(":"):
        if value.strip():
            roots.append(Path(value.strip()))
    prefixes = [(_os.environ.get("CONDA_PREFIX") or "").strip()]
    prefixes += [(_os.environ.get("CONDA_PREFIX_1") or "").strip()]
    for prefix in prefixes:
        if prefix:
            roots.append(Path(prefix).parent)          # <root>/envs/<name> -> <root>/envs
    for base in (home / "miniconda3", home / "anaconda3", home / "miniforge3",
                 home / "mambaforge", home / ".conda",
                 Path("C:/ProgramData/miniconda3"), Path("C:/ProgramData/anaconda3"),
                 Path("/opt/conda"), Path("/usr/local/conda")):
        roots.append(base / "envs")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for env in sorted(root.iterdir()):
                for exe in (env / "python.exe", env / "bin" / "python"):
                    if not exe.is_file():
                        continue
                    key = str(exe)
                    if key in seen:
                        break
                    seen.add(key)
                    out.append((f"conda env '{env.name}'", key))
                    break
        except Exception:                                        # noqa: BLE001
            continue
    return out


#: exe -> why the last probe could not finish. A probe that *timed out* has told us
#: nothing; a probe that ran and said "no" has told us something. Conflating the two made
#: a loaded laptop report a perfectly installed engine as missing, mid-sentence.
_PROBE_TROUBLE: dict[str, str] = {}


def probe_python(exe: str, modules: tuple[str, ...]) -> dict[str, bool]:
    """Which of `modules` can that interpreter import? One short child process.

    Deliberately tiny and quiet: no imports of ours, no output, 20 s cap. A python that
    cannot even start simply answers "no" to everything.
    """
    code = ("import importlib.util,json,sys;"
            "print(json.dumps({m: bool(importlib.util.find_spec(m)) for m in sys.argv[1:]}))")
    try:
        got = quiet.run([exe, "-c", code, *modules], capture_output=True, text=True,
                        timeout=20)
        if got.returncode != 0:              # it ran and refused: that IS an answer
            _PROBE_TROUBLE.pop(exe, None)
            return {m: False for m in modules}
        _PROBE_TROUBLE.pop(exe, None)
        import json
        data = json.loads((got.stdout or "{}").strip().splitlines()[-1] or "{}")
        return {m: bool(data.get(m)) for m in modules}
    except Exception as exc:                                     # noqa: BLE001
        _PROBE_TROUBLE[exe] = type(exc).__name__
        return {m: False for m in modules}


#: engine -> (when the answer was measured, the python that has it). The probe starts a
#: child process, so it must never run on the thread that is drawing a dialog: the first
#: version did, and Settings hung with a spinner ("struck aagi nikithu", 20.png).
_FOREIGN: dict[str, tuple[float, str]] = {}
_FOREIGN_SECONDS = 600.0
_FOREIGN_BUSY: set[str] = set()


def foreign_cached(engine: str, warm: bool = True) -> str:
    """The interpreter that already has `engine`, from cache only — never blocks.

    `warm=True` starts the real probe in the background when the cache is cold, so the
    answer is there next time the screen is opened.
    """
    now = time.monotonic()
    when, where = _FOREIGN.get(engine, (0.0, ""))
    if when and (now - when) < _FOREIGN_SECONDS:
        return where
    if warm:
        warm_foreign(engine)
    return ""


def foreign_version() -> float:
    """A number that changes whenever a background probe answers something new.

    The engine screen needs this. Before it, a probe finished *after* the dialog had
    already painted "not installed", and nothing ever re-read it — so a person with a
    perfectly good terminal install kept seeing "not installed" on a screen that was
    telling the truth about 30 seconds ago. `clone.engines()` caches for 30 s, so the
    screen needed a cheap way to notice the cache was stale.
    """
    try:
        return round(sum(when for when, _where in _FOREIGN.values()), 6)
    except Exception:                                            # noqa: BLE001
        return 0.0


def warm_foreign(engine: str) -> None:
    """Measure it in a daemon thread, once per engine."""
    if engine in _FOREIGN_BUSY:
        return
    _FOREIGN_BUSY.add(engine)

    def look() -> None:
        try:
            found = find_engine_python(engine)
        except Exception:                                        # noqa: BLE001
            found = ""
        _FOREIGN[engine] = (time.monotonic(), found)
        _FOREIGN_BUSY.discard(engine)

    try:
        threading.Thread(target=look, name=f"arc-engine-probe-{engine}",
                         daemon=True).start()
    except Exception:                                            # noqa: BLE001
        _FOREIGN_BUSY.discard(engine)


def find_engine_python(engine: str) -> str:
    """The interpreter that already has this engine's packages ('' if none)."""
    modules = _ENGINE_MODULES.get(engine, ())
    if not modules:
        return ""
    troubled = False
    for _label, exe in interpreters():
        have = probe_python(exe, modules)
        if all(have.values()):
            _FOREIGN[engine] = (time.monotonic(), exe)
            return exe
        if _PROBE_TROUBLE.get(exe):
            troubled = True
    if troubled and _FOREIGN.get(engine, (0.0, ""))[1]:
        # One interpreter could not answer (busy laptop, antivirus, a cold DLL cache).
        # Keep the last true answer instead of declaring the engine gone.
        return _FOREIGN[engine][1]
    if not troubled:
        _FOREIGN[engine] = (time.monotonic(), "")
    return ""


def diagnose() -> dict:
    """A report a person can read: who has what, and where the weights are."""
    from . import clone
    rows: list[dict] = []
    for label, exe in interpreters():
        have = probe_python(exe, ("transformers", "torch", "TTS", "piper"))
        rows.append({"label": label, "python": exe,
                     "has": [m for m, ok in have.items() if ok]})
    weights = {}
    for model in ("IndicF5", "xtts_v2"):
        path = clone._model_dir(model)                            # noqa: SLF001
        weights[model] = str(path) if path else ""
    return {"interpreters": rows, "weights": weights,
            "sidecar": str(sidecar_python()) if sidecar_python().exists() else ""}


def diagnosis_text() -> str:
    """The same thing as sentences, for the log box under the engine buttons."""
    got = diagnose()
    lines = ["which python has what (checked just now):"]
    for row in got["interpreters"]:
        has = ", ".join(row["has"]) or "nothing relevant"
        lines.append(f"  {row['label']:<16} {row['python']}")
        lines.append(f"  {'':<16} has: {has}")
    for model, path in got["weights"].items():
        lines.append(f"  weights {model:<10} {path or 'not found in the Hugging Face cache'}")
    if not any("transformers" in r["has"] for r in got["interpreters"]):
        lines.append("  no python here has transformers — it is not installed anywhere "
                     "on this PC yet")
    return "\n".join(lines)


def sidecar_python() -> Path:
    d = sidecar_dir()
    win = d / "Scripts" / "python.exe"
    if win.exists():
        return win
    return d / "bin" / "python"


def sidecar_flag(engine: str) -> Path:
    return sidecar_dir() / f"ready-{engine}.txt"


def sidecar_ready(engine: str) -> bool:
    """True only when the venv exists AND the warm-up for THAT engine finished."""
    return sidecar_python().exists() and sidecar_flag(engine).exists()


def sidecar_any() -> bool:
    return any(sidecar_ready(k) for k in SPECS)


def script_path(name: str) -> Path:
    """tools/<name> both in the repo and inside the frozen app (bundled as data)."""
    for base in (_app_dir(), Path(getattr(sys, "_MEIPASS", "")), ROOT):
        if not str(base):
            continue
        p = base / "tools" / name
        if p.is_file():
            return p
    return _app_dir() / "tools" / name


def _make_venv(target: Path, on_line: Line, cancel) -> dict:
    py = external_python() or ("" if getattr(sys, "frozen", False) else sys.executable)
    if not py:
        return {"ok": False, "code": -1, "why": "no Python on this computer", "last": ""}
    base = [py] if not py.endswith("py.exe") and Path(py).name != "py" else [py, "-3"]
    return _run([*base, "-m", "venv", str(target)], on_line, cancel)


def ensure_sidecar(engine: str, on_line: Line | None = None,
                   cancel: threading.Event | None = None,
                   on_progress: Progress | None = None) -> dict:
    """Build the borrowed environment and fill it with one engine. One button, no console."""
    say: Line = on_line or (lambda _l: None)
    lines: list[str] = []

    def note(text: str) -> None:
        lines.append(text)
        say(text)

    spec = SPECS[engine]
    target = sidecar_dir()
    note(f"a private engine folder for this app: {target}")
    if not sidecar_python().exists():
        note(f"step 1 of 3 · creating it with the Python already on this computer "
             f"({external_python() or 'not found'})")
        got = _make_venv(target, note, cancel)
        if not got["ok"]:
            note(f"could not create it ({got['why']}). Last line: {got['last'][:160]}")
            return {"ok": False, "engine": engine, "why": got["why"], "lines": lines}
    else:
        note("step 1 of 3 · the folder already exists")

    note(f"step 2 of 3 · {spec['label']} packages, about {spec['size_mb'] / 1000:.1f} GB "
         f"including the model")
    heavy, rest = split_packages(spec["packages"])
    if heavy:
        got = _run([str(sidecar_python()), "-m", "pip", "install", "--index-url",
                    _TORCH_CPU_INDEX, *heavy], note, cancel, on_progress)
        if not got["ok"]:
            note(f"{', '.join(heavy)} did not install ({got['why']}; "
                 f"last line: {got['last'][:160]})")
            return {"ok": False, "engine": engine, "why": got["why"], "lines": lines}
    got = _run([str(sidecar_python()), "-m", "pip", "install", *rest],
               note, cancel, on_progress)
    if not got["ok"]:
        note(f"packages did not install ({got['why']}; last line: {got['last'][:160]})")
        return {"ok": False, "engine": engine, "why": got["why"], "lines": lines}

    note("step 3 of 3 · the weights")
    gated: dict = {}          # filled in only if the weights turned out to be gated
    already = local_copy(engine)
    if already:
        note(f"the weights are already on this PC — using {already} instead of "
             f"downloading them again")
    warm = _run([str(sidecar_python()), "-c", spec["warm"]], note, cancel, on_progress)
    if not warm["ok"]:
        # The library could not get the weights itself. That happens for reasons that
        # have nothing to do with the person's connection (a hub version mismatch, a 401
        # worded as OSError, a wheel that is newer than the code that calls it) — and a
        # plain HTTPS GET of the same URLs works, which is exactly what a terminal user
        # sees. So do that, then ask the library one more time.
        note(f"the library could not fetch them ({warm['why']}) — downloading the files "
             f"directly instead")
        got_files = fetch(engine, on_line=note, on_progress=on_progress, cancel=cancel)
        if got_files.get("ok"):
            note("the files are in place — asking the library to load them")
            warm = _run([str(sidecar_python()), "-c", spec["warm"]], note, cancel,
                        on_progress)
        else:
            # The reason stays the library's own failure: it is the line the person can
            # act on, and swapping it for the fetch's reason is how "cannot reach
            # huggingface.co" turned into a licence message in the first place.
            note(f"the direct download did not finish either ({got_files.get('why')})")
            if got_files.get("needs_token"):
                gated = {"engine": engine, "needs_token": True,
                         "url": got_files.get("url", "")}
            else:
                gated = {}
    if not warm["ok"]:
        note(f"weights did not arrive ({warm['why']}; last line: {warm['last'][:160]})")
        note("nothing is ready yet. The packages are in place, so pressing Install again "
             "only re-fetches the weights — and until one engine finishes JARVIS keeps "
             "saying 'system voice', out loud, instead of pretending.")
        out = {"ok": False, "engine": engine, "why": warm["why"], "lines": lines}
        out.update(gated)
        return out

    try:
        sidecar_flag(engine).parent.mkdir(parents=True, exist_ok=True)
        sidecar_flag(engine).write_text(spec["label"], encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        note(f"the engine works but the note that records it did not save ({exc})")
    note(f"{spec['label']} is ready — replies in {spec['langs']} will use the voice you "
         f"chose. Speaking takes a few seconds on a CPU; that is the model, not a bug.")
    return {"ok": True, "engine": engine, "why": "", "lines": lines}


def sidecar_speak(text: str, lang: str, ref: str, transcript: str = "",
                  out_wav: str = "", engine: str = "", python: str = "") -> dict:
    """Hand one sentence to the borrowed interpreter; get a wav back. Nothing else."""
    engine = engine or ("indicf5" if (lang or "en").split("-")[0] == "ta" else "xtts")
    # `python` lets us use an interpreter the person already installed the engine into
    # (a terminal `pip install`, another venv) instead of asking for a second 1.5 GB.
    if not python and not sidecar_ready(engine):
        return {"ok": False, "why": f"the {engine} engine is not installed",
                "wav": ""}
    script = script_path("clone_speak.py")
    if not script.is_file():
        return {"ok": False, "why": f"{script.name} is missing from the app", "wav": ""}
    argv = [str(python or sidecar_python()), str(script), "--engine", engine, "--text", text,
            "--reference", str(ref), "--out", str(out_wav),
            "--lang", (lang or "en").split("-")[0]]
    if transcript:
        argv += ["--transcript", transcript]
    # A sentence is not a download: it has to answer in human time. The first run imports
    # a big library and loads a model, which is slow but bounded; a hung engine is not,
    # and a reply voice that blocks forever is the same failure as a dead window.
    import threading as _threading
    cancel = _threading.Event()
    timer = _threading.Timer(180.0, cancel.set)
    timer.daemon = True
    timer.start()
    try:
        got = _run(argv, lambda _l: None, cancel)
    finally:
        timer.cancel()
    if not got["ok"]:
        if cancel.is_set():
            return {"ok": False, "why": "the engine took longer than 3 minutes to answer "
                                        "a sentence — it is not ready yet", "wav": ""}
        return {"ok": False, "why": got["last"] or got["why"], "wav": ""}
    import os as _os
    if out_wav and _os.path.exists(out_wav) and _os.path.getsize(out_wav) > 1024:
        return {"ok": True, "why": "", "wav": out_wav}
    return {"ok": False, "why": "the engine ran but wrote no audio", "wav": ""}


# pip's `--progress-bar` choices moved under us: pip 24 accepted `ascii`, pip 26 offers
# only [auto, on, off, raw]. The old code appended `--progress-bar ascii` unconditionally,
# and pip answered `option --progress-bar: invalid choice: 'ascii'` — exit code 2, before a
# single byte was fetched. That is the whole of "clone voice la voice download aaga matiku":
# the download never started, and nothing on the screen said why.
_BAR_OK: dict[str, str] = {}


def bar_choice(python: str) -> str:
    """Which progress-bar spelling this pip understands: 'raw', 'ascii', 'on' or ''.

    Asked once per interpreter (a --help run costs a fifth of a second and nothing else),
    then remembered. '' means "pass no flag", which is always valid.
    """
    key = str(python)
    if key in _BAR_OK:
        return _BAR_OK[key]
    choice = ""
    try:
        # through quiet, like every other spawn in this app: a bare subprocess.run
        # flashes a console window on Windows, which is the one thing this project
        # promised never to do (tests/test_quiet.py enforces it).
        got = quiet.run([key, "-m", "pip", "install", "--help"],
                        capture_output=True, text=True, timeout=25)
        text = (got.stdout or "") + (got.stderr or "")
        cut = text.find("--progress-bar")
        if cut >= 0:
            window = text[cut:cut + 700]
            for name in ("raw", "ascii", "on"):        # most machine-readable first
                if name in window:
                    choice = name
                    break
    except Exception:                                    # noqa: BLE001
        choice = ""
    _BAR_OK[key] = choice
    return choice


def _is_bar_error(text: str) -> bool:
    return "progress-bar" in text and "invalid choice" in text


def _run(argv: list[str], on_line: Line, cancel: threading.Event | None,
         on_progress: Progress | None = None) -> dict:
    """Run a child process and stream both streams into `on_line`.

    Kept as one small seam so tests can replace it and prove the logic without
    downloading 3.4 GB.
    """
    # `--progress-bar ascii` makes pip draw a plain bar even when it is not talking to a
    # terminal, which is exactly what this is: a pipe. Without it pip prints one line and
    # then says nothing for minutes.
    want_bar = len(argv) > 3 and argv[1:4] == ["-m", "pip", "install"]
    if want_bar and "--progress-bar" not in argv:
        choice = bar_choice(argv[0])
        if choice:
            argv = [*argv, "--progress-bar", choice]
        want_bar = bool(choice)
    env = dict(os.environ, PYTHONUNBUFFERED="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    secret = token()
    if secret:                       # gated models read HF_TOKEN from the environment
        env["HF_TOKEN"] = secret
        env["HUGGING_FACE_HUB_TOKEN"] = secret
    try:
        proc = quiet.popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env=env)
    except Exception as exc:  # noqa: BLE001 — must be reported, not raised
        return {"ok": False, "code": -1, "why": f"could not start: {exc}", "last": ""}
    last = ""
    assert proc.stdout is not None

    def handle(piece: str) -> None:
        """One piece of output: a log line, or a progress reading, or both."""
        nonlocal last
        line = piece.strip()
        if not line:
            return
        reading = read_progress(line)
        if reading is not None:
            if on_progress is not None:
                on_progress(reading)
            return                          # bars do not belong in the log
        last = line
        on_line(line)

    # The pipe is read on its own thread and this loop POLLS it. Reading the pipe
    # directly here meant `read()` blocked until the child printed something, so a silent
    # stage (a big wheel with no output, a stalled connection) made Stop do nothing at
    # all — the button was pressed and the screen did not change, which is the report
    # "Stop aana pannalum stuck aagi nikkithu".
    import queue as _queue

    pieces: "_queue.Queue" = _queue.Queue()

    def reader() -> None:
        try:
            while True:
                piece = proc.stdout.read(512)
                if not piece:
                    break
                pieces.put(piece)
        except Exception:                                        # noqa: BLE001
            pass
        finally:
            pieces.put(None)

    threading.Thread(target=reader, name="arc-pipe-reader", daemon=True).start()

    def stop_now() -> dict:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:                                        # noqa: BLE001
            proc.kill()
        return {"ok": False, "code": -2, "why": "cancelled", "last": last}

    pending = ""
    while True:
        if cancel is not None and cancel.is_set():
            return stop_now()
        try:
            chunk = pieces.get(timeout=0.25)      # short poll: Stop answers in a moment
        except _queue.Empty:
            continue
        if chunk is None:
            break
        if isinstance(chunk, bytes):
            pending += chunk.decode("utf-8", "replace")
        else:                               # a test double handing back text
            pending += chunk
        while True:
            cut = min((i for i in (pending.find("\r"), pending.find("\n")) if i >= 0),
                      default=-1)
            if cut < 0:
                break
            handle(pending[:cut])
            pending = pending[cut + 1:]
        if len(pending) > 4096:             # a runaway bar with no newline
            handle(pending)
            pending = ""
    handle(pending)
    code = proc.wait()
    if code != 0 and want_bar and _is_bar_error(last):
        # A pip newer than this app: it told us the flag, so believe it, forget the cached
        # answer and run the same command once without a bar. Two seconds, no download lost.
        _BAR_OK[str(argv[0])] = ""
        on_line("this pip spells the progress bar differently — running again without it")
        retry, drop = [], False
        for arg in argv:
            if drop:
                drop = False
                continue
            if arg == "--progress-bar":
                drop = True
                continue
            retry.append(arg)
        return _run(retry, on_line, cancel, on_progress)
    return {"ok": code == 0, "code": code,
            "why": "" if code == 0 else f"exit code {code}", "last": last}


def install(engine: str, on_line: Line | None = None,
            cancel: threading.Event | None = None,
            on_progress: Progress | None = None) -> dict:
    """Make one engine real: packages first, then the weights.

    Returns {"ok", "engine", "lines", "why"} — and `ok` means the warm-up step ran,
    which is the only thing that proves the weights are there.
    """
    say: Line = on_line or (lambda _l: None)
    if engine not in SPECS:
        return {"ok": False, "engine": engine, "why": f"unknown engine {engine!r}",
                "lines": []}
    spec = SPECS[engine]
    m = method()
    lines: list[str] = []

    def note(text: str) -> None:
        lines.append(text)
        say(text)

    note(f"{spec['label']} for {spec['langs']} — about {spec['size_mb'] / 1000:.1f} GB, "
         f"once. Internet needed. {spec['needs']}.")

    if not m["can_install"]:
        note(f"cannot install from here: {m['why']}")
        return {"ok": False, "engine": engine, "why": m["why"] or "no pip", "lines": lines}

    state = gate(engine)
    if state.get("gated"):
        note(f"{spec['label']} is a gated model: Hugging Face will not hand over a single "
             f"file until its licence is accepted once. Nothing was downloaded.")
        for line in gate_advice(engine).splitlines():
            note(line)
        return {"ok": False, "engine": engine, "why": "gated model — needs a token",
                "needs_token": True, "url": state.get("url", ""), "lines": lines}
    if state.get("unknown"):
        note("could not reach Hugging Face to check the licence — trying anyway")

    # ALWAYS the private folder — frozen build or plain checkout. Reason, in the person's
    # words: "piper and innoru voice tool install pananum then application auto close
    # aaguthu." A `pip install` aimed at the environment the app is RUNNING in swaps files
    # under a live process (coqui-tts even pins an older numpy), and the next import can
    # end the window with no traceback. The private folder costs nothing: the app simply
    # calls that interpreter, exactly as the frozen build already did.
    need, have = space_needed_gb(engine), free_gb()
    if have >= 0 and have < need:
        note(f"there is not enough room: {spec['label']} needs about {need:g} GB free "
             f"(model plus the unpacked packages) and this drive has {have:.1f} GB.")
        note("nothing was downloaded. Free the space first — that is the only thing "
             "wrong here, and doing it after a 1.9 GB start would waste the download.")
        return {"ok": False, "engine": engine, "needs_space": True,
                "why": f"not enough free space — needs about {need:g} GB, has "
                       f"{have:.1f} GB", "lines": lines}
    note(f"room check: {have:.1f} GB free, this needs about {need:g} GB.")

    note("the engine goes into its own folder, not into the app's own packages: a pip run "
         "aimed at a running app can swap files under it, and that is what used to close "
         "the window")
    return ensure_sidecar(engine, on_line=say, cancel=cancel, on_progress=on_progress)

# ------------------------------------------------------- is it already on this PC?
def _repo_dir(repo: str) -> Path:
    return hf_home() / "hub" / ("models--" + repo.replace("/", "--"))


def _has_essential(snapshot: Path, engine: str) -> bool:
    marks = ESSENTIAL.get(engine, ())
    if not marks:
        return False
    if engine == "piper":                    # a piper voice is any matching onnx pair
        return any(snapshot.rglob("*.onnx.json")) or any(snapshot.rglob("*.onnx"))
    return all((snapshot / name).exists() or any(snapshot.rglob(name)) for name in marks)


def local_copy(engine: str) -> str:
    """Path of a complete copy of this engine's weights already on this computer.

    The report behind this: *"indicF5, xtts v2 also direct download aagum through
    terminal"* — so the person already HAS the model. Downloading 1.5 GB a second time
    into a second place is how an app tells someone their work did not count. The
    Hugging Face cache is the same cache a terminal download fills, so this asks it
    first and uses it as-is.
    """
    repo = MODEL_REPO.get(engine)
    if not repo:
        return ""
    snaps = _repo_dir(repo) / "snapshots"
    try:
        for snap in sorted(snaps.glob("*"), key=lambda q: q.stat().st_mtime, reverse=True):
            if _has_essential(snap, engine):
                return str(snap)
    except Exception:                                            # noqa: BLE001
        return ""
    return ""


def _api(repo: str, token: str = "", timeout: float = 25.0) -> dict:
    """The repo's file list, straight from the API. One request, no library."""
    import json
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"https://huggingface.co/api/models/{repo}",
                                 headers={"User-Agent": "arcdesk"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as got:
            return json.loads(got.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        return {"_status": exc.code}
    except Exception as exc:                                     # noqa: BLE001
        return {"_status": 0, "_why": f"{type(exc).__name__}: {exc}"}


def _skip_file(name: str) -> bool:
    low = name.lower()
    return (name.startswith("samples/") or "__pycache__" in low or low.endswith(".pyc")
            or low in (".gitattributes",) or low.startswith(".git/"))


def fetch(engine: str, on_line: Line | None = None, on_progress: Progress | None = None,
          cancel: threading.Event | None = None) -> dict:
    """Download the weights directly over HTTPS, into the cache everything else reads.

    Why this exists: the app used to download weights only as a side effect of
    `transformers` / `coqui-tts` "warming up". When that library fails — a hub version
    mismatch, a 401 the library words as `OSError: gated repo`, a wheel that is not
    installed yet — there is no download, and no way to have one. A terminal `wget` of
    the same URLs works fine, which is exactly what the person reported.

    This is that download: one HTTP GET per file, `Range` resume for anything that
    stopped, the same `snapshots/<sha>/…` layout the Hugging Face cache uses, and the
    same progress numbers as pip. The token, if there is one, comes from wherever it is
    already stored (`token_source`), so a machine that downloaded this in a terminal
    needs no new step.
    """
    import time as _t
    import urllib.error
    import urllib.request

    say: Line = on_line or (lambda _l: None)
    repo = MODEL_REPO.get(engine)
    if not repo:
        return {"ok": False, "why": f"{engine} has no model repository", "lines": []}
    token, where = token_source()
    lines: list[str] = []

    def note(text: str) -> None:
        lines.append(text)
        say(text)

    note(f"asking Hugging Face what {repo} contains"
         + (f" — using the token from {where}" if token else " — no token on this PC"))
    info = _api(repo, token)
    # 0 is a real answer from `_api` ("no answer at all"), so it must not be read as
    # "fine, carry on": `or 200` silently turned an offline machine into a download.
    status = 200 if info.get("_status") is None else int(info.get("_status") or 0)
    if status in (401, 403):
        note(f"Hugging Face refused the file list (HTTP {status}). This model needs a "
             f"token before any byte can be fetched.")
        return {"ok": False, "needs_token": True, "why": "gated model — needs a token",
                "url": f"https://huggingface.co/{repo}", "lines": lines}
    if status != 200:
        note(f"could not read the file list (HTTP {status or 'no answer'}"
             f"{'; ' + str(info.get('_why')) if info.get('_why') else ''})")
        return {"ok": False, "why": "could not reach Hugging Face", "lines": lines}

    sha = str(info.get("sha") or "main")
    files = [f.get("rfilename", "") for f in (info.get("siblings") or [])]
    files = [f for f in files if f and not _skip_file(f)]
    snapshot = _repo_dir(repo) / "snapshots" / sha
    snapshot.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/{repo}/resolve/{sha}/"

    def head_size(name: str) -> int:
        req = urllib.request.Request(base + name, method="HEAD",
                                     headers={"User-Agent": "arcdesk"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=25) as got:
                return int(got.headers.get("content-length") or 0)
        except Exception:                                        # noqa: BLE001
            return 0

    note(f"{len(files)} files · measuring the download first")
    sizes = {name: head_size(name) for name in files}
    total_mb = sum(sizes.values()) / 1e6
    note(f"{total_mb:,.0f} MB to fetch into {snapshot}")

    got_mb = sum((snapshot / n).stat().st_size for n in files
                 if (snapshot / n).exists()) / 1e6
    if on_progress:
        on_progress({"percent": round(got_mb / total_mb * 100, 1) if total_mb else 0.0,
                     "mb": round(got_mb, 1), "total_mb": round(total_mb, 1),
                     "speed": "", "eta": ""})

    started = _t.monotonic()
    for name in files:
        if cancel is not None and cancel.is_set():
            return {"ok": False, "why": "cancelled", "lines": lines}
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        want = sizes.get(name) or 0
        if target.exists() and want and target.stat().st_size == want:
            note(f"already here · {name}")
            continue
        have = target.stat().st_size if target.exists() else 0
        req = urllib.request.Request(base + name, headers={"User-Agent": "arcdesk"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        if have:
            req.add_header("Range", f"bytes={have}-")
            note(f"resuming · {name} at {have / 1e6:,.0f} MB")
        else:
            note(f"downloading · {name}")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp, open(target, "ab") as out:
                while True:
                    if cancel is not None and cancel.is_set():
                        return {"ok": False, "why": "cancelled", "lines": lines}
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    out.write(chunk)
                    have += len(chunk)
                    got_mb = sum((snapshot / n).stat().st_size for n in files
                                 if (snapshot / n).exists()) / 1e6
                    spent = max(_t.monotonic() - started, 0.001)
                    rate = got_mb / spent
                    left = (total_mb - got_mb) / rate if rate > 0 else 0.0   # seconds
                    if on_progress:
                        on_progress({
                            "percent": round(got_mb / total_mb * 100, 1) if total_mb else 0.0,
                            "mb": round(got_mb, 1), "total_mb": round(total_mb, 1),
                            "speed": f"{rate:.1f} MB/s",
                            "eta": (f"{int(left) // 60}:{int(left) % 60:02d}"
                                    if left >= 1 else "under a min"),
                        })
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return {"ok": False, "needs_token": True, "url": f"https://huggingface.co/{repo}",
                        "why": "gated model — needs a token", "lines": lines}
            return {"ok": False, "why": f"HTTP {exc.code} on {name}", "lines": lines}
        except Exception as exc:                                 # noqa: BLE001
            return {"ok": False, "why": f"{type(exc).__name__}: {exc}", "lines": lines}
        if want and target.stat().st_size != want:
            return {"ok": False, "why": f"{name} arrived short "
                                        f"({target.stat().st_size:,} of {want:,} bytes)",
                    "lines": lines}

    try:                                     # the ref huggingface_hub looks up first
        refs = _repo_dir(repo) / "refs"
        refs.mkdir(parents=True, exist_ok=True)
        (refs / "main").write_text(sha, encoding="utf-8")
    except Exception:                                            # noqa: BLE001
        pass
    if on_progress:
        on_progress({"percent": 100.0, "mb": round(total_mb, 1), "total_mb": round(total_mb, 1),
                     "speed": "", "eta": ""})
    note(f"done · {total_mb:,.0f} MB in {snapshot}")
    return {"ok": _has_essential(snapshot, engine), "path": str(snapshot),
            "mb": round(total_mb, 1), "lines": lines,
            "why": "" if _has_essential(snapshot, engine) else "the files arrived but the "
                                                                "engine's own files are missing"}


def missing_only(engine: str, on_line: Line | None = None,
                 on_progress: Progress | None = None,
                 cancel: threading.Event | None = None) -> dict:
    """Download only the part of an engine that is not on this PC yet.

    The report: "through the terminal all engines downloaded machi but ipo kanom" — so
    the packages are here and only the weights are not (a gated download that stopped, a
    voice file never fetched). Re-running the whole install would create a second venv
    and fetch a second copy of torch, which is exactly what an app must not do to someone
    who did the work already. This fetches the missing half and nothing else.
    """
    say: Line = on_line or (lambda _l: None)
    if engine == "piper":
        say("the piper engine is already on this PC — only its voice files are missing "
            "(~60 MB per language).")
        try:
            from . import piper_engine
            exe = piper_engine.python_with_piper() or external_python() or sys.executable
        except Exception:                                        # noqa: BLE001
            exe = external_python() or sys.executable
        say(f"downloading the voices with {exe}")
        got = _run([str(exe), "-c", _PIPER_WARM], say, cancel, on_progress)
        try:
            from . import clone, piper_engine
            from .ai.voice import piper_voices
            piper_engine.refresh()
            clone.refresh()
            voices = len(piper_voices())
        except Exception:                                        # noqa: BLE001
            voices = 0
        ok = voices > 0
        got.update(ok=ok, engine=engine, voices=voices,
                   why="" if ok else (got.get("why") or "no voice file arrived"))
        say(f"piper voices now on this PC: {voices}")
        return got
    got = fetch(engine, on_line=say, on_progress=on_progress, cancel=cancel)
    got.setdefault("engine", engine)
    return got


# ------------------------------------------------------------------ auto download
# Which engine a language needs. Tamil and Hindi belong to IndicF5; English to XTTS.
# Kept here as data so "download the right one automatically" is testable without a
# download, and so the app and the .bat cannot disagree about it.
CLONE_FOR_LANG = {
    "ta": "indicf5", "hi": "indicf5", "kn": "indicf5", "te": "indicf5", "ml": "indicf5",
    "bn": "indicf5", "gu": "indicf5", "mr": "indicf5", "pa": "indicf5", "or": "indicf5",
    "as": "indicf5", "en": "xtts",
}


def pick(lang: str = "", prefer: str = "") -> str:
    """The engine to download for this language. One answer, no menu."""
    if prefer in SPECS:
        return prefer
    code = (lang or "ta").split("-")[0].strip().lower()
    return CLONE_FOR_LANG.get(code, "xtts")


def free_gb(path: str | Path | None = None) -> float:
    """Free space on the drive that will hold the model, in GB."""
    import shutil
    try:
        target = Path(path) if path else sidecar_dir().parent
        while not target.exists() and target != target.parent:
            target = target.parent
        return shutil.disk_usage(str(target)).free / (1024 ** 3)
    except Exception:                                            # noqa: BLE001
        return -1.0


def space_needed_gb(engine: str) -> float:
    """Room a full install actually takes.

    The model size is the headline, but pip unpacks torch beside it and keeps the
    downloaded wheels in a cache, so a 1.9 GB engine wants about twice that.
    """
    return round(SPECS[engine]["size_mb"] / 1000.0 * 2.2, 1)


def _temporary(got: dict) -> bool:
    """A failure worth one automatic retry: the wire, not the model."""
    why = (str(got.get("why") or "") + " " + str(got.get("last") or "")).lower()
    return any(word in why for word in (
        "timed out", "timeout", "connection", "temporary failure", "network",
        "could not start", "exit code 137", "reset by peer", "incompleteread",
        "remote end closed", "ssl", "proxy"))


def auto(engine: str = "", lang: str = "", on_line: Line | None = None,
         on_progress: Progress | None = None, cancel: threading.Event | None = None,
         ask_token: Callable[[str, str], "str | None"] | None = None,
         tries: int = 2, pause: float = 3.0) -> dict:
    """Download the right engine, start to finish, with no second decision from anyone.

    The report this answers (26.png): "clone voice la voice download aaga matiku" —
    the download never began. Two of the reasons were ours, not the internet's:

      * IndicF5 is gated, so `install()` refused before fetching a byte and printed
        "press Install again" after the token. Nothing ever started, and the screen
        looked broken rather than blocked. Now the token is asked for *during* the
        same run and the download continues in the same run.
      * a temporary wire failure (proxy, timeout, a dropped wheel) ended the whole
        thing. One automatic retry covers the case where pressing the button again
        would have worked.

    `ask_token(engine, url)` is the only thing this can stop for, and it has to
    return a token or None. It is a callback so the dialog can show a paste box and
    the console can use input() without this module knowing about either.
    """
    say: Line = on_line or (lambda _l: None)
    chosen = pick(lang, engine)
    spec = SPECS[chosen]
    lines: list[str] = []

    def note(text: str) -> None:
        lines.append(text)
        say(text)

    note(f"downloading the engine for {(lang or 'ta')}: {spec['label']} "
         f"({spec['langs']}), about {spec['size_mb'] / 1000:.1f} GB, once.")
    if on_progress is not None:
        on_progress({"percent": 0, "mb": 0.0, "total_mb": float(spec["size_mb"]),
                     "speed": "", "eta": "starting"})

    asked = False
    calls = 0
    allowance = max(1, tries)          # a token is not a failed attempt: it buys one more
    while calls < allowance:
        calls += 1
        got = install(chosen, on_line=say, cancel=cancel, on_progress=on_progress)
        got.setdefault("engine", chosen)
        got["attempts"] = calls
        if got.get("ok"):
            note(f"{spec['label']} is ready.")
            got["lines"] = lines + list(got.get("lines") or [])
            return got

        if got.get("needs_token") and not asked and ask_token is not None:
            asked = True
            note(f"{spec['label']} is gated — it needs a free token once. Asking now.")
            answer = ask_token(chosen, str(got.get("url") or ""))
            if answer:
                set_token(answer)
                note("token saved for this run — continuing the download by itself.")
                allowance += 1
                continue
            note("no token given, so nothing was downloaded. That is fine: JARVIS keeps "
                 "speaking in the system voice until you decide.")
            got["lines"] = lines + list(got.get("lines") or [])
            return got

        if got.get("needs_space") or got.get("needs_token"):
            got["lines"] = lines + list(got.get("lines") or [])
            return got
        if calls < allowance and _temporary(got):
            note(f"that looked like the connection, not the model — trying once more "
                 f"in {pause:g} s.")
            if cancel is not None:
                if cancel.wait(pause):
                    got["why"] = "cancelled"
                    got["lines"] = lines + list(got.get("lines") or [])
                    return got
            else:
                time.sleep(pause)
            continue
        got["lines"] = lines + list(got.get("lines") or [])
        return got

    got = {"ok": False, "engine": chosen, "why": "out of attempts", "lines": lines}
    return got


def easiest() -> dict:
    """The engine to suggest to someone whose download is not going well.

    Piper: ~60 MB, no torch, no GPU, CPU-fast. If even that fails, the Windows voice
    needs nothing at all — it is already on the PC, and fix28 made it speak slowly and
    with an accent.
    """
    return dict(SPECS["piper"], id="piper")


def summary() -> str:
    """Plain multi-line text for a console or a tool dialog."""
    m = method()
    rows = []
    for v in status().values():
        state = "ready" if v["ready"] else f"missing ({v['problem'] or 'not installed'})"
        rows.append(f"  {v['label']:<10} {v['langs']:<14} {v['size_mb']:>5} MB  {state}")
    head = ("  install route: " + ("pip (this build can do it in one click)"
                                   if m["can_install"] else m["why"]))
    return "\n".join([head, *rows])
