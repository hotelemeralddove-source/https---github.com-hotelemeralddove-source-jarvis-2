"""Who is allowed to wake JARVIS — one voice, enrolled on this machine.

The ask: *"intha laptop-la jarvis enoda voice-la mattum work aaganum; vera laptop-la
naan install pannina anga vera person-oda voice-la access aaganum."*

So: a **speaker profile per machine**. `enroll()` builds a fingerprint from 3 short
recordings of one person; `verify()` compares whatever woke ARC against it. Profiles
live in the app's data folder, so a second laptop has its own list and nothing is
shared unless a person copies the folder deliberately.

**This is a convenience filter, not a security control.** Say it once, clearly:

* it stops your family, your TV and a YouTube video in the room from waking ARC;
* it does **not** stop a recording of you — a phone playing your voice back scores
  high. Nothing that runs on one microphone can tell a human from a good speaker;
* the models are ~30 MB and run on the CPU (sherpa-onnx speaker embeddings), which is
  why this is opt-in and never on by default.

When no embedding engine is installed, `available()` is False and the app falls back
to the plain wake word and *says so* — it never silently pretends to be locked.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

DEFAULT_THRESHOLD = 0.62        # cosine similarity; tuned so "same person" passes
MARGIN = 0.06                   # best profile must beat the runner-up by this much


# ------------------------------------------------------------------- storage
def _dir() -> Path:
    from . import config
    d = config.data_dir() / "voiceid"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _profiles_file() -> Path:
    return _dir() / "profiles.json"


def profiles() -> dict:
    try:
        return json.loads(_profiles_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    tmp = _profiles_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(_profiles_file())


# ------------------------------------------------------------------- engine
def engine() -> dict:
    """Which speaker-embedding backend is usable right now, and why not if not."""
    try:
        import sherpa_onnx  # noqa: F401
        model = _find_model("speaker")
        if model:
            return {"name": "sherpa-onnx", "model": str(model), "ready": True, "why": ""}
        return {"name": "sherpa-onnx", "model": "", "ready": False,
                "why": "the speaker-embedding model (30 MB) is not downloaded yet — "
                       "the Voices window has the one-click download"}
    except Exception:
        pass
    try:
        import resemblyzer  # noqa: F401
        return {"name": "resemblyzer", "model": "", "ready": True, "why": ""}
    except Exception:
        pass
    return {"name": "", "model": "", "ready": False,
            "why": "no speaker-id engine installed — the Voices window offers it in one "
                   "click (sherpa-onnx plus its 30 MB speaker model)"}


def available() -> tuple[bool, str]:
    e = engine()
    return bool(e["ready"]), (e["why"] or "")


def _find_model(kind: str) -> Path | None:
    from . import config
    roots = [config.data_dir() / "models", Path.home() / ".cache" / "arcdesk" / "models"]
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.onnx"):
            low = p.name.lower()
            if (kind == "speaker") and ("speaker" in low or "eres" in low or "wespeaker" in low):
                return p
    return None


def embed(wav: str) -> list[float] | None:
    """A voice fingerprint (unit vector) for one WAV file, or None."""
    e = engine()
    if not e["ready"] or not wav:
        return None
    try:
        if e["name"] == "sherpa-onnx":
            return _sherpa_embed(wav, Path(e["model"]))
        if e["name"] == "resemblyzer":
            from resemblyzer import VoiceEncoder, preprocess_wav
            import numpy as np
            enc = VoiceEncoder()
            v = enc.embed_utterance(preprocess_wav(Path(wav)))
            return _unit(np.asarray(v, dtype=float).tolist())
    except Exception:
        return None
    return None


def _sherpa_embed(wav: str, model: Path) -> list[float] | None:
    import sherpa_onnx
    import wave
    cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(model),
                                                      num_threads=1)
    ex = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
    stream = ex.create_stream()
    with wave.open(wav) as w:
        sr = w.getframerate()
        if sr != 16000:
            return None                      # the model expects 16 kHz; the caller resamples
        while True:
            chunk = w.readframes(3200)
            if not chunk:
                break
            import array
            a = array.array("h")
            a.frombytes(chunk)
            stream.accept_waveform(16000, [s / 32768.0 for s in a])
    stream.input_finished()
    if not ex.is_ready(stream):
        return None
    # sherpa-onnx renamed this between releases: `compute_embedding` in older
    # builds, `compute` in 1.13.x. Ask for whichever this install has.
    compute = getattr(ex, "compute_embedding", None) or getattr(ex, "compute", None)
    if compute is None:
        return None
    return _unit(list(compute(stream)))


def _unit(vec: list[float]) -> list[float]:
    norm = sum(v * v for v in vec) ** 0.5 or 1e-9
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    return sum(x * y for x, y in zip(a, b)) / (
        (sum(x * x for x in a) ** 0.5 or 1e-9) * (sum(y * y for y in b) ** 0.5 or 1e-9))


def centroid(vectors: list[list[float]]) -> list[float]:
    """Average of several recordings, then re-normalised — steadier than one clip."""
    if not vectors:
        return []
    n = len(vectors)
    total = [0.0] * len(vectors[0])
    for v in vectors:
        for i, x in enumerate(v):
            total[i] += x
    return _unit([x / n for x in total])


# ------------------------------------------------------------------ enroll
def enroll(name: str, wavs: list[str], threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Build/refresh one person's profile from 2-5 recordings. Never raises."""
    name = (name or "").strip() or "me"
    ok, why = available()
    if not ok:
        return {"ok": False, "message": why}
    usable = [w for w in wavs if Path(str(w)).expanduser().exists()]
    if len(usable) < 2:
        return {"ok": False,
                "message": "give me at least 2 recordings (3 is better), 3-8 s each, "
                           "same person, quiet room"}
    vectors, skipped = [], []
    for w in usable:
        v = embed(str(Path(w).expanduser()))
        (vectors if v else skipped).append(w if not v else v)
    if len(vectors) < 2:
        return {"ok": False, "message": "could not read a voice from those files"}

    data = profiles()
    spread = [cosine(vectors[i], vectors[j])
              for i in range(len(vectors)) for j in range(i + 1, len(vectors))]
    lowest = min(spread) if spread else 0.0
    data[name] = {
        "vector": centroid(vectors),
        "samples": len(vectors),
        "self_similarity": round(lowest, 3),
        # a low self-similarity means the clips disagree — the threshold is raised
        # so this profile cannot accidentally match everyone
        "threshold": round(max(threshold, min(0.92, lowest - 0.12)), 3),
        "created": time.strftime("%Y-%m-%d %H:%M"),
    }
    _save(data)
    return {"ok": True, "name": name, "samples": len(vectors),
            "self_similarity": round(lowest, 3),
            "threshold": data[name]["threshold"],
            "skipped": len(skipped),
            "message": f"enrolled '{name}' from {len(vectors)} recordings"}


def forget(name: str) -> bool:
    data = profiles()
    if name not in data:
        return False
    del data[name]
    _save(data)
    return True


# ------------------------------------------------------------------ verify
def verify(wav: str, threshold: float = 0.0) -> dict:
    """Is this recording the enrolled person? {"ok", "who", "score", "allowed", "why"}."""
    data = profiles()
    if not data:
        return {"allowed": True, "who": "", "score": 0.0,
                "why": "nobody is enrolled — the wake word is not restricted"}
    ok, why = available()
    if not ok:
        return {"allowed": True, "who": "", "score": 0.0,
                "why": f"voice lock is on but cannot run: {why}"}
    vec = embed(wav)
    if not vec:
        return {"allowed": False, "who": "", "score": 0.0,
                "why": "could not read a voice from that recording"}
    scored = sorted(((cosine(vec, p["vector"]), name) for name, p in data.items()),
                    reverse=True)
    best_score, best_name = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    need = max(float(data[best_name].get("threshold", DEFAULT_THRESHOLD)),
               threshold or 0.0)
    allowed = best_score >= need and (best_score - second) >= 0.0
    return {"allowed": bool(allowed), "who": best_name if allowed else "",
            "score": round(best_score, 3), "needed": need,
            "runner_up": round(second, 3),
            "why": "" if allowed else f"score {best_score:.2f} < {need:.2f}"}


SPEAKER_MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
                     "speaker-recongition-models/"
                     "3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx")


def download_model(target: str = "", progress=None) -> dict:
    """Fetch the ~30 MB speaker-embedding model. Visible, resumable-by-retry, honest.

    Lives here (not in the CLI tool) so the packaged app and the terminal share one
    implementation — the installer's post-install step calls this.
    """
    import urllib.request
    from . import config
    dest = Path(target).expanduser() if target else config.data_dir() / "models"
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / "speaker_embedding.onnx"
    if final.exists() and final.stat().st_size > 1_000_000:
        return {"ok": True, "path": str(final), "bytes": final.stat().st_size,
                "message": f"already present: {final}"}
    tmp = final.with_suffix(".part")
    try:
        with urllib.request.urlopen(SPEAKER_MODEL_URL, timeout=300) as r, tmp.open("wb") as fh:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                block = r.read(1 << 16)
                if not block:
                    break
                fh.write(block)
                done += len(block)
                if progress is not None and total:
                    progress(int(done * 100 / total))
        tmp.replace(final)
    except Exception as exc:                                    # noqa: BLE001
        try:
            tmp.unlink()
        except OSError:
            pass
        return {"ok": False, "path": "", "bytes": 0,
                "message": f"download failed: {type(exc).__name__}: {exc}. Put the file "
                           f"in {dest} by hand if your network blocks GitHub."}
    return {"ok": True, "path": str(final), "bytes": final.stat().st_size,
            "message": f"{final} ({final.stat().st_size // 1024} KB)"}


def describe() -> str:
    data = profiles()
    ok, why = available()
    if not ok:
        return f"voice lock: unavailable — {why}"
    if not data:
        return "voice lock: ready, nobody enrolled yet (anyone can wake it)"
    who = ", ".join(f"{n} ({p['samples']} clips)" for n, p in data.items())
    return f"voice lock: on for {who} · engine {engine()['name']}"


def copy_profiles_to(folder: str) -> str:
    """Carry an enrollment to another machine (optional, deliberate)."""
    target = Path(folder).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    src = _profiles_file()
    if not src.exists():
        return "nothing to copy — no profiles yet"
    shutil.copyfile(src, target / "arcdesk-voiceid-profiles.json")
    return f"copied profiles to {target}"
