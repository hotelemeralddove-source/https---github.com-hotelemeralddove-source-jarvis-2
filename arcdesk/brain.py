"""A brain in the box — a real local model, installed from inside the app.

The complaint was plain: *"no local model detected nu varuthu, brain ah add pana solluthu,
athayum oru bundle ah koduthudu"*. Telling somebody to go and install Ollama is not a
product; it is homework. So this module installs and runs a small local model itself:

    packages   llama-cpp-python[server]   into the app's own environment
    weights    a GGUF file, downloaded once, straight into the data folder
    service    `python -m llama_cpp.server`, bound to 127.0.0.1 only
    config     written for you: provider "custom", that URL, that model

Everything is optional and reversible, nothing runs at import time, and every failure
ends with a sentence a person can act on. Lite keeps working throughout — a brain that
is not ready must never be a dead app.

Sizes are stated before the download starts, from `MODELS`, because "how big" is the
question that decides whether a person clicks.
"""
from __future__ import annotations

import json
import os
import subprocess

from . import quiet
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

Line = Callable[[str], None]
PORT = 8010

MODELS: dict[str, dict] = {
    "small": {
        "label": "Qwen2.5 1.5B",
        "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": ("https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
                "resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
        "mb": 1066,
        "tools": True,
        "note": "can call the tools (it opens apps, reads the system). ~1.5 GB of RAM "
                "while it runs.",
    },
    "tiny": {
        "label": "Qwen2.5 0.5B",
        "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "url": ("https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/"
                "resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"),
        "mb": 469,
        "tools": False,
        "note": "only for talking. Too small to drive the tools reliably, and this app "
                "will say so rather than let it try.",
    },
}
DEFAULT_MODEL = "small"
# A partly-downloaded file must never count as a model. (A module constant, not a
# literal, so the test can shrink it instead of filling a disk with a 60 MB fake.)
MIN_MODEL_BYTES = 50 * 1024 * 1024


# --------------------------------------------------------------------------- where
def models_dir() -> Path:
    from .config import data_dir
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def gguf_path(key: str = DEFAULT_MODEL) -> Path:
    return models_dir() / MODELS[key]["file"]


def model_present(key: str = DEFAULT_MODEL) -> bool:
    p = gguf_path(key)
    try:
        return p.is_file() and p.stat().st_size > MIN_MODEL_BYTES
    except Exception:
        return False


def installed_models() -> list[str]:
    return [k for k in MODELS if model_present(k)]


# --------------------------------------------------------------------------- which python
def _env_python() -> tuple[str, str]:
    """(interpreter, why-not) for the environment that will hold llama-cpp-python.

    Source build → this interpreter. Frozen build → the same private folder the voice
    engine uses (see `engines.py`), because a compiled .exe cannot import a package that
    arrives later and shipping torch/llama.cpp inside it would double the installer.
    """
    try:
        from . import engines
        m = engines.method()
    except Exception:
        m = {"frozen": False, "can_install": True, "why": ""}
    if not m.get("frozen"):
        return sys.executable, "" if m.get("can_install") else (m.get("why") or "")
    sid = engines.sidecar_python()
    if sid.exists():
        return str(sid), ""
    if not engines.external_python():
        return "", ("this is the installed app and no Python is installed on this "
                    "computer — the built-in brain needs one: python.org, default "
                    "options, then press Install again")
    return "", "the app's private environment is not built yet (Settings → Voice → Get "
    "the reply-voice engine… builds it, or press Install here and it will be made)"


# --------------------------------------------------------------------------- download
def download(key: str = DEFAULT_MODEL, on_line: Line | None = None,
             cancel: threading.Event | None = None) -> dict:
    """Fetch the GGUF once, resumably-by-retry, with the percentage visible."""
    say: Line = on_line or (lambda _l: None)
    spec = MODELS[key]
    dest = gguf_path(key)
    if model_present(key):
        say(f"{spec['label']}: already on disk ({dest})")
        return {"ok": True, "path": str(dest), "why": ""}
    part = dest.with_suffix(".part")
    say(f"downloading {spec['label']} — {spec['mb']} MB, once, from huggingface.co")
    done = 0
    try:
        req = urllib.request.Request(spec["url"], headers={"User-Agent": "ArcDesk"})
        with urllib.request.urlopen(req, timeout=60) as r, part.open("wb") as fh:
            total = int(r.headers.get("Content-Length") or 0)
            step = max(1, total // 20) if total else 4 * 1024 * 1024
            next_mark = step
            while True:
                if cancel is not None and cancel.is_set():
                    part.unlink(missing_ok=True)
                    return {"ok": False, "path": "", "why": "cancelled"}
                block = r.read(1 << 16)
                if not block:
                    break
                fh.write(block)
                done += len(block)
                if done >= next_mark:
                    pct = f"{100 * done / total:.0f}%" if total else f"{done >> 20} MB"
                    say(f"  {pct}")
                    next_mark += step
        part.replace(dest)
    except Exception as exc:                                   # noqa: BLE001
        part.unlink(missing_ok=True)
        say(f"the download failed: {type(exc).__name__}: {exc}")
        return {"ok": False, "path": "", "why": f"{type(exc).__name__}: {exc}"}
    say(f"saved to {dest}")
    return {"ok": True, "path": str(dest), "why": ""}


def ensure_packages(on_line: Line | None = None,
                    cancel: threading.Event | None = None) -> dict:
    """llama-cpp-python + its little web server. ~40 MB of wheels, no compiler needed."""
    say: Line = on_line or (lambda _l: None)
    py, why = _env_python()
    if not py:
        say(why)
        return {"ok": False, "why": why}
    say("installing llama-cpp-python[server] (about 40 MB of wheels)")
    from .engines import _run
    got = _run([py, "-m", "pip", "install", "llama-cpp-python[server]"], say, cancel)
    if not got["ok"]:
        say(f"that failed ({got['why']}): {got['last'][:160]}")
    return {"ok": bool(got["ok"]), "why": got["why"]}


# --------------------------------------------------------------------------- the service
_SERVER: subprocess.Popen | None = None


def _port_open(port: int = PORT, timeout: float = 0.25) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except Exception:
        return False


#: The last answer to "is the local brain up?", and when it was taken. Only the main
#: thread reads this — see `running()`.
_RUN_CACHE: dict = {"at": 0.0, "value": False}
_RUN_SECONDS = 8.0
_RUN_WARMING = None


def running(port: int = PORT, timeout: float = 0.25) -> bool:
    """Is the local brain answering — answered WITHOUT opening a socket on the UI thread.

    A refused connect is instant, but a port that is filtered or a machine under load can
    sit there for the whole timeout, and this is asked while a dialog is drawing. On the
    main thread the answer is the last known one (and a background check is started); on a
    worker, or from a tool, it is the real check, now.
    """
    import threading
    import time

    def real() -> bool:
        if _SERVER is not None and _SERVER.poll() is None and _port_open(port, timeout):
            return True
        return _port_open(port, timeout)

    if threading.current_thread() is not threading.main_thread():
        value = real()
        _RUN_CACHE.update(at=time.monotonic(), value=value)
        return value

    now = time.monotonic()
    stale = (now - _RUN_CACHE["at"]) > _RUN_SECONDS
    if stale and not (_RUN_WARMING is not None and _RUN_WARMING.is_alive()):
        def warm() -> None:
            _RUN_CACHE.update(at=time.monotonic(), value=real())

        globals()["_RUN_WARMING"] = threading.Thread(target=warm, name="arc-brain-probe",
                                                     daemon=True)
        _RUN_WARMING.start()
    return bool(_RUN_CACHE["value"])


def start_server(key: str = DEFAULT_MODEL, port: int = PORT,
                 on_line: Line | None = None, wait: float = 90.0) -> dict:
    """Start the local model server and wait until it really answers."""
    global _SERVER
    say: Line = on_line or (lambda _l: None)
    if running(port):
        say(f"a brain is already answering on 127.0.0.1:{port}")
        return {"ok": True, "why": "", "url": f"http://127.0.0.1:{port}/v1"}
    if not model_present(key):
        return {"ok": False, "why": f"{MODELS[key]['label']} is not downloaded yet", "url": ""}
    py, why = _env_python()
    if not py:
        return {"ok": False, "why": why, "url": ""}
    argv = [py, "-m", "llama_cpp.server", "--model", str(gguf_path(key)),
            "--host", "127.0.0.1", "--port", str(port), "--n_ctx", "4096",
            "--n_threads", str(max(2, (os.cpu_count() or 4) // 2))]
    say("starting the local model (this loads the file once; a few seconds)")
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        _SERVER = quiet.popen(argv, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, creationflags=flags)
    except Exception as exc:                                   # noqa: BLE001
        return {"ok": False, "why": f"could not start it: {exc}", "url": ""}
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if _SERVER.poll() is not None:
            tail = ""
            try:
                tail = (_SERVER.stderr.read() or b"").decode("utf-8", "replace")[-300:]
            except Exception:
                pass
            return {"ok": False, "why": f"it exited at once. {tail}".strip(), "url": ""}
        if _port_open(port):
            say(f"ready on 127.0.0.1:{port} — the built-in brain is answering now")
            return {"ok": True, "why": "", "url": f"http://127.0.0.1:{port}/v1"}
        time.sleep(0.5)
    return {"ok": False, "why": "it did not answer within 90 s (a very slow CPU); try "
                                "the smaller model", "url": ""}


def stop_server() -> bool:
    global _SERVER
    if _SERVER is None:
        return False
    try:
        _SERVER.terminate()
        _SERVER.wait(timeout=8)
    except Exception:
        try:
            _SERVER.kill()
        except Exception:
            pass
    _SERVER = None
    return True


def apply_config(cfg: dict, key: str = DEFAULT_MODEL, port: int = PORT) -> dict:
    """Point the app at the built-in brain. Idempotent, and saved atomically."""
    ai = cfg.setdefault("ai", {})
    ai.update({"enabled": True, "provider": "custom",
               "base_url": f"http://127.0.0.1:{port}/v1",
               "model": MODELS[key]["label"].replace(" ", "-").lower()})
    try:
        from . import config as _config
        _config.save(cfg)
    except Exception:
        pass
    return ai


#: Last "which other local engines are up?" answer, and when it was taken. `status()` is
#: painted into the HUD every few seconds, so it may not open ten sockets while it runs.
_OTHERS: dict = {"at": 0.0, "value": []}
_OTHERS_SECONDS = 20.0
_OTHERS_WARMING = None


def _others() -> list[str]:
    """Other local engines that are up — measured, but never on the drawing thread.

    `backends.probe()` opens one socket per backend, ten of them, 0.25 s timeout each. In
    the HUD that is a freeze of up to 2.5 s every time the row is repainted (`20.png`, and
    the older "lag aaguthu" report). A worker gets the truth immediately; the main thread
    gets the last answer and starts a background check if the answer is stale.
    """
    import threading
    import time

    def real() -> list[str]:
        try:
            from .ai import backends
            return [d.describe() for d in backends.probe()]
        except Exception:                                        # noqa: BLE001
            return []

    if threading.current_thread() is not threading.main_thread():
        value = real()
        _OTHERS.update(at=time.monotonic(), value=value)
        return value

    stale = (time.monotonic() - _OTHERS["at"]) > _OTHERS_SECONDS
    if stale and not (_OTHERS_WARMING is not None and _OTHERS_WARMING.is_alive()):
        def warm() -> None:
            _OTHERS.update(at=time.monotonic(), value=real())

        globals()["_OTHERS_WARMING"] = threading.Thread(target=warm, name="arc-backend-probe",
                                                        daemon=True)
        _OTHERS_WARMING.start()
    return list(_OTHERS["value"])


# --------------------------------------------------------------------------- status
def status() -> dict:
    """Everything a person needs to know, measured — never guessed."""
    others = _others()
    have = installed_models()
    up = running()
    from . import identity
    if up:
        sentence = ("the built-in brain is running on 127.0.0.1:%d — %s thinks for "
                    "itself, offline." % (PORT, identity.DEFAULT_NAME))
    elif have:
        sentence = ("%s is downloaded but not running — press Start." %
                    MODELS[have[0]]["label"])
    elif others:
        sentence = "a local model is already running: " + ", ".join(others)
    else:
        sentence = ("no local model yet — Lite answers instantly offline; press Install "
                    "for a real brain (one download, no account).")
    return {
        "models": {k: {"label": v["label"], "mb": v["mb"], "present": model_present(k),
                       "tools": v["tools"], "note": v["note"]} for k, v in MODELS.items()},
        "installed": have,
        "running": up,
        "port": PORT,
        "others": others,
        "sentence": sentence,
        "python": _env_python()[0],
    }


def summary() -> str:
    st = status()
    rows = [f"  brain: {st['sentence']}", f"  server: 127.0.0.1:{st['port']} "
            f"{'running' if st['running'] else 'stopped'}"]
    for k, v in st["models"].items():
        rows.append(f"  {v['label']:<14} {v['mb']:>5} MB  "
                    f"{'downloaded' if v['present'] else 'not downloaded'}"
                    f"  {'tool calling' if v['tools'] else 'chat only'}")
    if st["others"]:
        rows.append("  also running: " + ", ".join(st["others"]))
    return "\n".join(rows)
