"""A library of voices — the two roles, kept separate.

The concept, in the user's own words:

    "voice command input is my voice. jarvis reply pana vendiya voice nan choose panra
     or upload voice — nan enoda voice la pesuven, command panuven, jarvis rajini voice
     la enakku reply panum."

So there are two lists, and they are not the same list:

    COMMAND voices  who is allowed to say "hey jarvis" and be obeyed
                    stored as speaker embeddings by arcdesk/voiceid.py (any number of
                    people; verify() accepts the best match)
    REPLY voice     which voice ARC answers in
                    a reference clip + its transcript, stored here

Everything is per machine and reversible. A reply voice can be any voice you have a
recording of — including one that is not yours — and the app never claims a system voice
is that voice: if no clone engine is installed it says so out loud.

Licence, stated once, not repeated at you: cloning a real person's voice so that it says
things they never said is a legal and personal problem, not a technical one. Use voices you
have the right to use (your own, or someone who said yes).
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
import wave
from pathlib import Path

from . import config


# --------------------------------------------------------------------- storage
def voice_dir() -> Path:
    d = config.data_dir() / "voices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_file() -> Path:
    return voice_dir() / "voices.json"


def _read() -> dict:
    try:
        data = json.loads(_index_file().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("reply", [])
            data.setdefault("active_reply", "")
            return data
    except Exception:
        pass
    return {"reply": [], "active_reply": ""}


def _write(data: dict) -> None:
    tmp = _index_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(_index_file())


# ------------------------------------------------------------------ reply voices
def reply_voices() -> list[dict]:
    """Every voice you have given JARVIS to answer in."""
    return list(_read().get("reply") or [])


def active_reply() -> dict:
    """The reply voice in use, or {} — never guesses."""
    data = _read()
    wanted = data.get("active_reply") or ""
    for entry in data.get("reply") or []:
        if entry.get("id") == wanted and Path(entry.get("path", "")).exists():
            return entry
    for entry in data.get("reply") or []:          # a deleted file must not silence it
        if Path(entry.get("path", "")).exists():
            return entry
    return {}


def reply_clip() -> str:
    entry = active_reply()
    return entry.get("path", "") if entry else ""


def set_reply(voice_id: str) -> bool:
    data = _read()
    if not any(e.get("id") == voice_id for e in data.get("reply") or []):
        return False
    data["active_reply"] = voice_id
    _write(data)
    # keep the old single-reference path in sync: every other part of the app (clone.py,
    # the daemon, the CLI) already reads reference.wav, and two sources of truth is how
    # a reply voice silently stops working.
    entry = next(e for e in data["reply"] if e.get("id") == voice_id)
    _mirror_to_clone(Path(entry["path"]), entry.get("transcript", ""))
    return True


def _mirror_to_clone(clip: Path, text: str) -> None:
    try:
        from . import clone
        target = clone.voice_dir() / "reference.wav"
        shutil.copyfile(clip, target)
        (clone.voice_dir() / "reference.txt").write_text((text or "").strip() + "\n",
                                                         encoding="utf-8")
    except Exception:
        pass


def remove_reply(voice_id: str) -> bool:
    data = _read()
    keep = [e for e in data.get("reply") or [] if e.get("id") != voice_id]
    if len(keep) == len(data.get("reply") or []):
        return False
    gone = next(e for e in data["reply"] if e.get("id") == voice_id)
    data["reply"] = keep
    if data.get("active_reply") == voice_id:
        data["active_reply"] = keep[0]["id"] if keep else ""
        if keep:
            _mirror_to_clone(Path(keep[0]["path"]), keep[0].get("transcript", ""))
    _write(data)
    try:
        Path(gone.get("path", "")).unlink(missing_ok=True)
    except Exception:
        pass
    return True


# ----------------------------------------------------------------------- adding
def add_reply(name: str, src: str, transcript: str = "", lang: str = "auto") -> dict:
    """Import a recording as a NEW reply voice (kept as its own file, graded)."""
    from . import clone

    source = Path(str(src)).expanduser()
    if not source.exists():
        return {"ok": False, "message": f"no such file: {source}"}
    label = (name or "").strip() or source.stem
    got = clone.import_reference(str(source), transcript)      # convert + grade + cut
    if not got.get("ok"):
        return {"ok": False, "message": got.get("message", "could not import that clip")}

    # import_reference writes the shared reference.wav; copy it to this voice's own file
    # BEFORE anything else can overwrite it.
    voice_id = uuid.uuid4().hex[:8]
    target = voice_dir() / f"{voice_id}.wav"
    shutil.copyfile(got["path"], target)

    entry = {"id": voice_id, "name": label, "path": str(target),
             "seconds": got.get("seconds", 0.0), "grade": got.get("grade", ""),
             "snr_db": got.get("snr_db", 0.0), "advice": got.get("advice", ""),
             "transcript": (transcript or "").strip(), "lang": lang or "auto",
             "created": int(time.time())}
    data = _read()
    data.setdefault("reply", []).append(entry)
    if not data.get("active_reply"):
        data["active_reply"] = voice_id
    _write(data)
    # Say what will actually happen next, in the same breath as "added". The complaint was
    # an imported clip that the app then never used, with nothing anywhere explaining why.
    next_step = ""
    try:
        from . import clone as _clone, voicematch
        ready = [k for k, v in _clone.engines().items() if v.get("available")]
        if ready:
            next_step = f" — replies will use {ready[0]}"
        elif voicematch.active():
            pitch = (voicematch.reference_profile() or {}).get("pitch")
            next_step = (f" — replies will now speak at your pitch ({pitch} Hz) straight "
                         f"away, no download needed")
        else:
            next_step = (" — no clone engine installed and matching is off: turn on "
                         "\"Speak in my voice\" in Settings → Voice")
    except Exception:                                            # noqa: BLE001
        next_step = ""
    return {"ok": True, "voice": entry,
            "message": f"added “{label}”: {entry['seconds']:g} s, {entry['grade']}"
                       f"{' — ' + entry['advice'] if entry['advice'] else ''}{next_step}"}


# ------------------------------------------------------------- command voices
def _slice(path: Path, want: int = 3, each: float = 3.0) -> list[str]:
    """Cut a clip into `want` short 16 kHz mono takes for the speaker model.

    The speaker model wants 16 kHz; a single long recording as one take still works, but
    three short ones give the enrolment a centroid instead of one point, which is what
    makes the lock accept a normal speaking voice and reject someone else.
    """
    from . import clone

    # Any file the person has — mp3, WhatsApp .opus, m4a — not just WAV. Before this,
    # enrolling a command voice from an mp3 raised "unknown format" deeper in.
    samples, sr = clone.load_audio(path)
    if sr != 16000:
        samples = clone._resample(samples, sr, 16000)      # noqa: SLF001
        sr = 16000
    total = len(samples) / sr
    if total < each * 1.2:
        return [str(path)]
    per = min(each, total / want)
    out: list[str] = []
    for i in range(want):
        start = int(i * (total - per) / max(1, want - 1) * sr)
        piece = samples[start:start + int(per * sr)]
        if len(piece) < sr:                                 # under a second: useless
            continue
        target = voice_dir() / f"take-{uuid.uuid4().hex[:6]}.wav"
        clone._write_mono(piece, sr, target)                # noqa: SLF001
        out.append(str(target))
    return out or [str(path)]


def add_command(name: str, src: str) -> dict:
    """Allow one more voice to command JARVIS, from a recording of that voice."""
    from . import voiceid

    label = (name or "").strip() or "voice"
    source = Path(str(src)).expanduser()
    if not source.exists():
        return {"ok": False, "message": f"no such file: {source}"}
    takes = _slice(source)
    got = voiceid.enroll(label, takes)
    for take in takes:
        if take != str(source):
            try:
                Path(take).unlink(missing_ok=True)
            except Exception:
                pass
    if not got.get("ok"):
        return {"ok": False, "message": got.get("message", "could not enrol that voice")}
    return {"ok": True, "name": label,
            "message": f"“{label}” may now command JARVIS (agreement {got.get('self_similarity', 0):.2f})"}


def command_voices() -> list[str]:
    from . import voiceid
    return sorted(voiceid.profiles())


def remove_command(name: str) -> bool:
    from . import voiceid
    return voiceid.forget(name)


# ------------------------------------------------------------------- one line
def describe() -> str:
    """What governs the microphone and what governs the reply — in words."""
    who = command_voices()
    reply = active_reply()
    left = ", ".join(who) if who else "anybody (voice lock off)"
    right = (f"{reply['name']} ({reply['seconds']:g} s)" if reply else "the system voice")
    if len(who) > 1:
        left = f"{left} (any of them)"
    return f"command: {left} · reply: {right}"
