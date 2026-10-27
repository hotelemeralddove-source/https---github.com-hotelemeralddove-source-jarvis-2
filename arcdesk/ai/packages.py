"""Ask the catalogue questions, and look at this PC to answer them.

`catalog.py` is the data; this module is the only code that touches it. Two jobs:

  * **search** — "which open-source project can read a PDF?" over name, role,
    job, notes and tags, ranked simply and printed for a chat transcript.
  * **detect** — is it actually installed here? A 120 ms TCP connect to localhost,
    a `shutil.which`, or an import probe. Read-only, no installs, no internet.

Kept out of `catalog.py` on purpose: the data module must stay importable by a
linter with no side effects, and a socket probe is a side effect.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import socket
from pathlib import Path

from .catalog import BY_KEY, CATALOG, REFUSED, Package, by_role, wired


def _port_open(port: int, timeout: float = 0.12) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _pip_has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def detect(p: Package) -> bool | None:
    """True / False when we can check, None when the row has no detector."""
    if not p.detect:
        return None
    kind, _, value = p.detect.partition(":")
    try:
        if kind == "port":
            return _port_open(int(value))
        if kind == "exe":
            return shutil.which(value) is not None
        if kind == "pip":
            return _pip_has(value)
        if kind == "file":
            return Path(os.path.expanduser(value)).exists()
    except Exception:
        return False
    return None


def scan(role: str = "") -> list[tuple[Package, bool | None]]:
    rows = [(p, detect(p)) for p in CATALOG if not role or p.role == role]
    return rows


# ------------------------------------------------------------------ searching
def search(query: str = "", role: str = "", limit: int = 8) -> list[Package]:
    """Rank the catalogue against a sentence. Words, not substrings."""
    words = [w for w in "".join(c if c.isalnum() else " " for c in query.lower()).split()
             if len(w) > 2]
    pool = list(by_role(role)) if role else list(CATALOG)
    if not words:
        return pool[:limit]

    scored: list[tuple[int, Package]] = []
    for p in pool:
        blob = " ".join((p.name, p.role, p.job, p.note, p.install,
                         " ".join(p.tags))).lower()
        # word boundaries, not substrings: "read" must not match "already"
        tokens = set("".join(c if c.isalnum() else " " for c in blob).split())
        def matches(word: str) -> bool:
            if word in tokens:
                return True
            return len(word) > 3 and any(t.startswith(word) for t in tokens)
        hits = sum(1 for w in words if matches(w))
        if not hits:
            continue
        score = hits * 3
        score += 2 if any(w in p.name.lower() for w in words) else 0
        score += 3 if any(w == p.role for w in words) else 0
        score += 1 if p.arc_uses else 0
        scored.append((score, p))
    scored.sort(key=lambda row: (-row[0], row[1].name))
    return [p for _, p in scored[:limit]]


# ------------------------------------------------------------------ formatting
def _line(p: Package, status: bool | None = None, show_install: bool = True) -> str:
    head = f"  · {p.name} ({p.licence}) — {p.job}"
    bits = [head]
    if p.repo:
        bits.append(f"github.com/{p.repo}")
    if status is True:
        bits.append("installed")
    elif status is False and show_install and p.install:
        bits.append("missing → " + p.install)
    if p.arc_uses:
        bits.append("JARVIS uses it")
    return "\n    ".join(bits)


def list_text(query: str = "", role: str = "", limit: int = 8) -> str:
    if role and role not in {p.role for p in CATALOG}:
        return (f"No group called {role!r}. Groups: "
                + ", ".join(sorted({p.role for p in CATALOG})))
    hits = search(query, role, limit)
    if not hits:
        return (f"Nothing in the catalogue matches {query!r}. It has "
                f"{len(CATALOG)} packages — ask 'all packages' to see them by group.")
    title = (f"{len(hits)} of {len(CATALOG)} open-source packages matching "
             f"{query!r}" if query else f"{len(hits)} of {len(CATALOG)} packages")
    return title + ":\n" + "\n".join(_line(p) for p in hits)


def scan_text(role: str = "") -> str:
    rows = scan(role)
    found = [p for p, st in rows if st is True]
    checkable = [(p, st) for p, st in rows if st is not None]
    head = (f"{len(found)} of {len(checkable)} checkable packages are on this PC "
            f"({len(CATALOG)} catalogued).")
    if not found:
        return head + "\nNothing detected. Ask 'what is missing' for the exact commands."
    lines = [_line(p, status=True, show_install=False) for p in found]
    return head + "\n" + "\n".join(lines)


def plan_text(role: str = "", limit: int = 12) -> str:
    missing = [(p, st) for p, st in scan(role) if st is False and p.install]
    if not missing:
        return "Nothing missing — every checkable package is already installed."
    lines = [f"  · {p.name}: {p.install}" for p, _ in missing[:limit]]
    more = ("" if len(missing) <= limit
            else f"\n  … and {len(missing) - limit} more; ask for a group like "
                 f"'missing ears' to narrow it.")
    return (f"{len(missing)} missing packages, all free and account-free:\n"
            + "\n".join(lines) + more)


def summary_text() -> str:
    counts: dict[str, int] = {}
    for p in CATALOG:
        counts[p.role] = counts.get(p.role, 0) + 1
    groups = ", ".join(f"{role} {n}" for role, n in sorted(counts.items()))
    return (f"{len(CATALOG)} GitHub packages catalogued ({groups}); "
            f"{len(wired())} wired into JARVIS today; 0 cost money.")


def detail(key: str) -> str:
    p = BY_KEY.get(key.lower().strip())
    if p is None:
        return f"No package called {key!r}. " + summary_text()
    status = detect(p)
    state = ("installed here" if status else
             "not detected here" if status is False else "no automatic check")
    parts = [f"{p.name} — {p.role} — {p.licence} — {state}",
             p.job]
    if p.repo:
        parts.append("github.com/" + p.repo)
    if p.install:
        parts.append("install: " + p.install)
    if p.note:
        parts.append(p.note)
    if p.arc_uses:
        parts.append("Arc Desk already talks to it.")
    return "\n".join(parts)


def refused_text() -> str:
    return "Deliberately not used:\n" + "\n".join(f"  ✗ {n} — {w}" for n, w in REFUSED)
