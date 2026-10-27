"""The shortcut on the Desktop: made once, repaired when the folder moves.

The report: *"desktop shortcut um ila, proper ah open panra options um ila"*. A shortcut
that points at an old folder's run.py is worse than no shortcut at all — it looks right,
does nothing, and the person concludes the app is broken. So the same rule as the auto-start
entry: make it once, keep it pointing at THIS folder, and never recreate one you deleted.

Pure functions live in `tools/shortcut.py` (target, args, icon, paths); this file is the
part that decides *whether* to act, so it can be checked without Windows.
"""
from __future__ import annotations

import json
from pathlib import Path


def state_path() -> Path:
    from . import config
    return config.data_dir() / "shortcut.json"


def _read() -> dict:
    try:
        path = state_path()
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:                                            # noqa: BLE001
        return {}


def _write(data: dict) -> None:
    try:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except Exception:                                            # noqa: BLE001
        pass


def _tool():
    """tools/shortcut.py, loaded as a module (it is a script, not a package)."""
    import importlib.util
    from . import engines
    path = engines.script_path("shortcut.py")
    spec = importlib.util.spec_from_file_location("arcdesk_shortcut_tool", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def decide(known: dict, now: dict) -> str:
    """What to do, from what was recorded and what is on disk. No side effects.

    * "create"  — never offered before: make it (a first launch should end with something
                  to click, not with a .bat file to remember)
    * "repair"  — the shortcut is there but points at an old folder
    * "restore" — it was created before and is now missing: the person deleted it, or a
                  cleaner did. Recreate once, quietly, because "it disappeared" is the
                  complaint that started this.
    * "none"    — everything is already right, or they turned it off in Settings
    """
    if known.get("off"):
        return "none"
    if not now.get("desktop"):
        return "restore" if known.get("made") else "create"
    if str(known.get("folder") or "") != str(now.get("folder") or ""):
        return "repair"
    return "none"


def ensure(force: bool = False) -> dict:
    """Do the above for real. Returns {action, made, why} — never raises."""
    try:
        tool = _tool()
        now = tool.status()
        now["folder"] = str(Path(__file__).resolve().parents[1])
        known = _read()
        action = "create" if force else decide(known, now)
        if action == "none":
            return {"action": "none", "made": [], "why": ""}
        got = tool.create()
        if not got.get("ok"):
            _write({**known, "last_error": str(got.get("why") or "")})
            return {"action": "failed", "made": [], "why": got.get("why") or ""}
        made = [str(p) if not isinstance(p, str) else p for p in got.get("made") or []]
        _write({"made": True, "folder": now["folder"], "paths": made,
                "target": got.get("target", ""), "off": bool(known.get("off"))})
        return {"action": action, "made": made, "why": ""}
    except Exception as exc:                                     # noqa: BLE001
        return {"action": "failed", "made": [], "why": f"{type(exc).__name__}: {exc}"}


def set_preference(on: bool) -> dict:
    """Settings has one checkbox: keep a shortcut on the Desktop, or do not."""
    known = _read()
    _write({**known, "off": not on})
    if not on:
        try:
            _tool().remove()
        except Exception:                                        # noqa: BLE001
            pass
        return {"action": "removed" if not on else "none"}
    return ensure(force=True)
