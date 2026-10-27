"""The Vault — where your work lives, and how it survives.

The question this module answers, in the user's words: *"naan jarvis la work panra
files, progress ellam enga save aagum?"* and *"venum na desktop la vera folder-la
save panikira mathiri irukanum"*.

Three rules, in this order:

  1. **Nothing of yours is ever the only copy.** Adding a file to a project COPIES it
     into the vault; your original stays exactly where it was, untouched. Exporting
     COPIES out again into a new timestamped folder. There is no "move" anywhere in
     this file.
  2. **Progress is saved as it happens**, not when you remember. Every answer, note and
     checkpoint is appended to `progress.jsonl` inside the project — one line, written
     atomically, so a crash or a power cut loses at most the line being written.
  3. **The vault is a plain folder.** No database, no lock-in, no proprietary format.
     You can open `%APPDATA%\\ArcDesk\\vault` in Explorer, copy it to a pen drive, or
     point the vault somewhere else (Settings → Vault) including a folder *outside*
     Arc Desk entirely.

Layout:

    <vault root>/
        index.json                 every project, newest first
        current.json               which project new work belongs to
        projects/<slug>/
            project.json           name, created, updated, note, counts
            notes.md               your notes, in order, readable in Notepad
            progress.jsonl         one JSON per line: time, note, and the answer
            files/                 anything you added (copies, never links)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

from . import config

# ---------------------------------------------------------------- small helpers


def _cfg() -> dict:
    try:
        return config.load()
    except Exception:
        return {}


def root() -> Path:
    """Where the vault lives. Configurable, and the config is read every time.

    `vault.root` may be anywhere — another drive, a synced folder, a pen drive. An
    empty value means the default inside Arc Desk's own data folder.
    """
    cfg = _cfg().get("vault") or {}
    custom = str(cfg.get("root") or "").strip()
    if custom:
        p = Path(os.path.expandvars(custom)).expanduser()
    elif cfg.get("portable"):
        # portable = next to the program, for a USB stick
        from . import paths
        p = paths.app_dir() / "vault"
    else:
        p = config.data_dir() / "vault"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _projects_dir() -> Path:
    d = root() / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def slug(name: str) -> str:
    """A folder name that is safe on every filesystem and still readable."""
    s = re.sub(r"[^A-Za-z0-9 _-]+", "", (name or "").strip()).strip()
    s = re.sub(r"\s+", "-", s).lower()
    return (s or "project")[:48]


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


# ---------------------------------------------------------------- projects


def project_dir(name: str) -> Path:
    return _projects_dir() / slug(name)


def create(name: str, note: str = "") -> dict:
    """Create (or reopen) a project. Reopening never clears anything."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "a project needs a name"}
    d = project_dir(name)
    meta_path = d / "project.json"
    existed = meta_path.is_file()
    d.mkdir(parents=True, exist_ok=True)
    (d / "files").mkdir(exist_ok=True)
    meta = _read_json(meta_path, {})
    meta.setdefault("name", name)
    meta.setdefault("slug", slug(name))
    meta.setdefault("created", _now())
    meta.setdefault("notes_count", 0)
    meta.setdefault("files_count", 0)
    meta["updated"] = _now()
    if note:
        meta["note"] = note
    _atomic_write(meta_path, json.dumps(meta, indent=1, ensure_ascii=False))
    set_current(name)
    return {"ok": True, "reopened": existed, "path": str(d), "project": meta}


def set_current(name: str) -> str:
    _atomic_write(root() / "current.json", json.dumps({"name": name, "at": _now()}))
    return name


def current() -> str:
    return str(_read_json(root() / "current.json", {}).get("name") or "")


def get(name: str = "") -> dict:
    """Project metadata, or {} if it does not exist yet."""
    name = name or current()
    if not name:
        return {}
    meta = _read_json(project_dir(name) / "project.json", None)
    return meta if isinstance(meta, dict) else {}


def projects() -> list[dict]:
    """Every project, newest activity first, with its measured size."""
    out = []
    for d in sorted(_projects_dir().iterdir() if _projects_dir().is_dir() else []):
        if not d.is_dir():
            continue
        meta = _read_json(d / "project.json", None)
        if not isinstance(meta, dict):
            continue
        out.append({
            "name": meta.get("name", d.name),
            "slug": d.name,
            "updated": meta.get("updated", ""),
            "notes": meta.get("notes_count", 0),
            "files": meta.get("files_count", 0),
            "_mtime": _mtime(d),
        })
    out.sort(key=lambda r: r["_mtime"], reverse=True)
    for row in out:
        row.pop("_mtime", None)
    return out


def _mtime(p: Path) -> float:
    try:
        return max((f.stat().st_mtime for f in p.rglob("*") if f.is_file()), default=0.0)
    except OSError:
        return 0.0


# ---------------------------------------------------------------- progress


def note(text: str, project: str = "") -> dict:
    """Append a note to notes.md. Readable in Notepad, append-only, never rewritten."""
    name = project or current()
    if not name:
        return {"ok": False, "error": "no project is open — say 'start a project called X'"}
    create(name)                     # idempotent; makes sure the folder exists
    d = project_dir(name)
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "nothing to save"}
    with open(d / "notes.md", "a", encoding="utf-8") as fh:
        fh.write(f"\n## {_now()}\n{text}\n")
    meta = get(name)
    meta["notes_count"] = int(meta.get("notes_count", 0)) + 1
    meta["updated"] = _now()
    _atomic_write(d / "project.json", json.dumps(meta, indent=1, ensure_ascii=False))
    return {"ok": True, "project": name, "path": str(d / "notes.md")}


def checkpoint(text: str = "", project: str = "", data: dict | None = None) -> dict:
    """Save one line of progress. Cheap enough to call on every answer.

    One JSON object per line in progress.jsonl:
        {"at": "...", "note": "...", "files": 3, "bytes": 1200, "data": {...}}

    Appending is atomic enough for this purpose (a single small write, O_APPEND), and
    a half-written last line is skipped by `resume()` instead of losing the file.
    """
    name = project or current()
    if not name:
        return {"ok": False, "skipped": "no project open"}
    if not project_dir(name).is_dir():
        create(name)
    d = project_dir(name)
    entry = {
        "at": _now(),
        "note": (text or "").strip()[:4000],
        "files": _count_files(d),
        "bytes": _size(d),
    }
    if data:
        entry["data"] = data
    try:
        path = d / "progress.jsonl"
        # If a previous write was cut off mid-line (power cut, full disk), the file does
        # not end in a newline. Appending straight onto it would glue the new record to
        # the broken one and lose BOTH — so repair the newline first.
        needs_newline = path.is_file() and path.stat().st_size > 0 and \
            not path.read_bytes()[-1:] == b"\n"
        with open(path, "a", encoding="utf-8") as fh:
            if needs_newline:
                fh.write("\n")
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "project": name, "at": entry["at"]}


def resume(project: str = "", lines: int = 5) -> dict:
    """What was I doing? — the last few checkpoints, plus the last note."""
    name = project or current()
    if not name or not project_dir(name).is_dir():
        known = ", ".join(p["name"] for p in projects()[:5]) or "none yet"
        return {"ok": False, "error": f"no project called {name or '(none given)'}",
                "known": known}
    d = project_dir(name)
    recent = []
    try:
        for raw in (d / "progress.jsonl").read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                recent.append(json.loads(raw))
            except json.JSONDecodeError:
                continue          # a torn last line is skipped, not fatal
    except OSError:
        pass
    notes_file = d / "notes.md"
    last_notes = notes_file.read_text(encoding="utf-8")[-1500:] if notes_file.is_file() else ""
    return {
        "ok": True,
        "project": name,
        "path": str(d),
        "checkpoints": len(recent),
        "recent": recent[-lines:],
        "notes_tail": last_notes,
        "files": sorted(p.name for p in (d / "files").glob("*"))[:40],
        "bytes": _size(d),
    }


# ---------------------------------------------------------------- moving data


def add(path: str, project: str = "") -> dict:
    """COPY a file or folder into the project. The original is never moved."""
    name = project or current()
    if not name:
        return {"ok": False, "error": "no project is open"}
    src = Path(os.path.expandvars(path or "")).expanduser()
    if not src.exists():
        return {"ok": False, "error": f"not found: {src}"}
    create(name)
    dest_dir = project_dir(name) / "files"
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name
    n = 2
    while target.exists():                       # never overwrite inside the vault
        target = dest_dir / f"{src.stem}-{n}{src.suffix}"
        n += 1
    try:
        if src.is_dir():
            shutil.copytree(src, target)
            count = sum(1 for _ in target.rglob("*") if _.is_file())
        else:
            shutil.copy2(src, target)            # copy2 keeps the mtime
            count = 1
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    meta = get(name)
    meta["files_count"] = int(meta.get("files_count", 0)) + count
    meta["updated"] = _now()
    _atomic_write(project_dir(name) / "project.json",
                  json.dumps(meta, indent=1, ensure_ascii=False))
    return {"ok": True, "project": name, "into": str(target), "files": count,
            "original_untouched": str(src)}


def _safe_dest(dest: str) -> Path:
    """Turn 'desktop', 'documents', 'downloads' or a path into a real folder."""
    key = (dest or "").strip().lower()
    home = Path.home()
    named = {
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "doc": home / "Documents",
        "downloads": home / "Downloads",
        "pictures": home / "Pictures",
        "home": home,
    }
    if key in named:
        p = named[key]
    elif key:
        p = Path(os.path.expandvars(dest)).expanduser()
    else:
        p = home / "Desktop"
    p.mkdir(parents=True, exist_ok=True)
    return p


def export(project: str = "", dest: str = "", verify: bool = True) -> dict:
    """COPY a project out to anywhere — Desktop, another folder, another drive.

    The vault copy stays. A new timestamped folder is created every time, so two
    exports never merge into one another.
    """
    name = project or current()
    if not name or not project_dir(name).is_dir():
        return {"ok": False, "error": f"no project called {name or '(none given)'}"}
    src = project_dir(name)
    try:
        target_parent = _safe_dest(dest)
    except OSError as exc:
        return {"ok": False, "error": f"cannot use that folder: {exc}"}
    if str(target_parent.resolve()).startswith(str(root().resolve())):
        return {"ok": False, "error": "that folder is inside the vault — choose "
                                      "somewhere else (Desktop, another drive)"}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = target_parent / f"ArcVault-{slug(name)}-{stamp}"
    n = 2
    while target.exists():
        target = target_parent / f"ArcVault-{slug(name)}-{stamp}-{n}"
        n += 1
    try:
        shutil.copytree(src, target)
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result = {"ok": True, "project": name, "to": str(target),
              "files": _count_files(target), "bytes": _size(target)}
    if verify:
        # prove the copy, like backup.py does — same rule, different folder
        a = sorted(p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file())
        b = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
        result["verified"] = a == b and all(
            (src / rel).stat().st_size == (target / rel).stat().st_size for rel in a)
    return result


# ---------------------------------------------------------------- numbers


def _count_files(p: Path) -> int:
    try:
        return sum(1 for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def _size(p: Path) -> int:
    try:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def stats() -> dict:
    tops = []
    for d in sorted(_projects_dir().iterdir()) if _projects_dir().is_dir() else []:
        if d.is_dir():
            tops.append((d.name, _size(d)))
    tops.sort(key=lambda x: x[1], reverse=True)
    return {
        "root": str(root()),
        "exists": root().is_dir(),
        "projects": len(tops),
        "bytes": sum(s for _n, s in tops),
        "megabytes": round(sum(s for _n, s in tops) / 1e6, 1),
        "current": current(),
        "biggest": [{"project": n, "mb": round(s / 1e6, 2)} for n, s in tops[:5]],
    }


def report(limit: int = 8) -> str:
    """One paragraph a human can read out loud."""
    s = stats()
    if not s["projects"]:
        return (f"Your vault is at {s['root']} and it is empty. Say "
                f"'start a project called <name>' and I will keep everything there.")
    rows = projects()[:limit]
    lines = [f"Vault: {s['root']} — {s['projects']} project(s), {s['megabytes']} MB."]
    for r in rows:
        mark = " ← open" if r["name"] == s["current"] else ""
        lines.append(f"  · {r['name']} — {r['notes']} notes, {r['files']} files, "
                     f"last saved {r['updated']}{mark}")
    return "\n".join(lines)
