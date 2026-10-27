"""Wire protocol between the Arc Desk window and the voice daemon.

Newline-delimited JSON over 127.0.0.1. Deliberately dumb and dependency-free so
either side can be written in anything later.

    {"event": "wake"}                        wake phrase fired
    {"event": "exit"}                        exit phrase fired ("bye jarvis")
    {"event": "text", "text": "open notepad"}  recognised command
    {"event": "status", "msg": "listening"}    daemon said something
    {"event": "error", "msg": "no microphone"} fatal, daemon is exiting
    {"event": "hello", "engine": "vosk", "phrase": "hey jarvis"}

Why TCP on loopback and not a named pipe: it works identically on Windows,
Linux and macOS, it is debuggable with netcat, and the OS keeps it local.
"""
from __future__ import annotations

import json

DEFAULT_PORT = 8765


def encode(event: str, **fields) -> bytes:
    payload = {"event": event}
    payload.update(fields)
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes | str) -> dict | None:
    try:
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None
