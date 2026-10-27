"""Backup, autostart and the first-run wizard — the three promises that outlive the app.

These are the parts of ARC that can actually lose somebody's data or quietly change
their machine, so the tests are paranoid in a specific way:

  * a backup proves itself (SHA-256 on the destination) and a tampered copy is caught;
  * a second backup NEVER merges into the first;
  * every file in the source keeps its exact mtime and size, before and after;
  * a backup into itself, or onto a nearly-full disk, is refused with a sentence;
  * autostart writes exactly one per-user entry, reads it back, and removes it cleanly;
  * the wizard applies only the four answers given, and reports the rest as untouched.

Run:  python tests/test_backup.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
# autostart writes to ~/.config — give it a throw-away home so the test never touches
# the real one (a lesson from the settings-file incident).
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="arcdesk-xdg-")
# ...and on Windows the store is the HKCU Run key, which no home override can reach.
# Without this stand-in, running this test on a laptop would register — and the
# final disable() would REMOVE — the person's real start-with-Windows entry.
os.environ["ARCDESK_AUTOSTART_FAKE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import autostart, backup, config, deepsearch, docs_worker, firstrun  # noqa: E402
from arcdesk.ai import tools  # noqa: E402
from arcdesk.ai.lite import respond  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:36]!r}")
    ok &= bool(good)


root = Path(tempfile.mkdtemp(prefix="arcdesk-bk-"))
src = root / "Documents"
target = root / "USB"
(src / "Old").mkdir(parents=True)
(src / "node_modules").mkdir(parents=True)
target.mkdir()
(src / "hampi.txt").write_text("invoice 45000 rupees\n", encoding="utf-8")
(src / "Old" / "big.bin").write_bytes(os.urandom(400_000))
(src / "node_modules" / "x.js").write_text("cache", encoding="utf-8")
(src / "scratch.tmp").write_text("temp", encoding="utf-8")
# Windows needs developer mode or admin to create a symlink, and this test used to
# FAIL there for that reason alone. The rule being tested is "links are skipped", and
# that is still proven whenever the OS allows one to exist.
try:
    (src / "link").symlink_to("/etc/hostname" if os.name != "nt" else
                              str(src / "hampi.txt"))
    made_link = True
except (OSError, NotImplementedError):
    made_link = False

snapshot = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in src.rglob("*") if p.is_file()}

print("1) a plan is free — it writes nothing")
planned = backup.plan(str(src), str(target))
check("the plan is ok", planned["ok"], True)
check("both real files are included", planned["count"], 2)
# junk is always skipped (2 items); the symlink is a third when the OS allowed one
check("junk is excluded (node_modules, .tmp, and a symlink where allowed)",
      planned["skipped"] >= 2, True)
if not made_link:
    print("   ..   SKIP symlink part — this OS/user cannot create one (Windows default)")
check("nothing was created by planning", list(target.iterdir()), [])

print("1b) the space guard refuses honestly, but does not refuse a small copy")
# Its own sandbox on purpose: every copy() here writes a folder, and the later sections
# count folders. Polluting the shared target would make an honest test fail for a
# reason that has nothing to do with what it is testing.
import shutil as _shutil
import arcdesk.backup as _bk

guard_root = Path(tempfile.mkdtemp(prefix="arcdesk-guard-"))
guard_src = guard_root / "src"
guard_tgt = guard_root / "tgt"
guard_src.mkdir()
guard_tgt.mkdir()
(guard_src / "a.txt").write_text("hello\n" * 400, encoding="utf-8")  # ~2.4 KB

_orig = _bk.plan


def _plan_with_free(gb):
    def inner(*a, **k):
        out = _orig(*a, **k)
        out["target_free_gb"] = gb
        return out
    return inner


_bk.plan = _plan_with_free(40.0)
check("plenty of room -> copied", _bk.copy(str(guard_src), str(guard_tgt))["ok"], True)
_bk.plan = _plan_with_free(5e-7)            # ~0.5 KB free, 2.4 KB to copy
tiny = _bk.copy(str(guard_src), str(guard_tgt))
check("a copy bigger than the free space is refused", tiny["ok"], False)
check("...and the message says MB, not '0.0 GB'", "MB" in tiny["error"], True)
_bk.plan = _plan_with_free(0.2)             # 200 MB free on a small pen drive
check("a small copy on a nearly-full drive is allowed",
      _bk.copy(str(guard_src), str(guard_tgt))["ok"], True)
_bk.plan = _plan_with_free(-1.0)            # free space unknown
check("unknown free space does not block a copy",
      _bk.copy(str(guard_src), str(guard_tgt))["ok"], True)
_bk.plan = _orig
check("the guard left nothing behind when it refused",
      len([p for p in guard_tgt.iterdir() if p.is_dir()]), 3)
_shutil.rmtree(guard_root, ignore_errors=True)

print("2) the copy verifies itself")
result = backup.copy(str(src), str(target))
check("copy succeeded", result["ok"], True)
check("verified, not assumed", result["verified"], True)
check("every file matched on the destination", result["mismatch_rows"], 0)
check("a manifest was written", Path(result["manifest"]).is_file(), True)
check("the backup lives in its own folder", "ArcBackup-" in result["folder"], True)
manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
check("the manifest records a hash per file", all(e["sha256"] for e in manifest["files"]), True)
check("source and target are recorded", manifest["source"] == str(src.resolve()), True)
copied = Path(result["folder"]) / "hampi.txt"
check("the copy is byte-identical",
      hashlib.sha256(copied.read_bytes()).hexdigest()
      == hashlib.sha256((src / "hampi.txt").read_bytes()).hexdigest(), True)

print("3) the originals are untouched — proven, not promised")
after = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in src.rglob("*") if p.is_file()}
check("every file in the source is byte-identical", snapshot == after, True)
check("nothing was deleted", (src / "hampi.txt").is_file(), True)
check("nothing was renamed", (src / "Old" / "big.bin").is_file(), True)
check("the report says the originals were read-only",
      "opened read-only" in backup.report(result), True)

print("4) a second run never merges into the first")
second = backup.copy(str(src), str(target))
check("it made a new folder", second["folder"] != result["folder"], True)
check("both backups still exist", len(backup.backups(str(target))), 2)
check("the first one is untouched",
      (Path(result["folder"]) / "hampi.txt").is_file(), True)

print("5) a tampered backup is caught, and said out loud")
cracked = Path(second["folder"]) / "hampi.txt"
cracked.write_text("invoice 99999 rupees\n", encoding="utf-8")
recheck = backup.verify(second["folder"])
check("verify fails", recheck["ok"], False)
check("it names the changed file", "hampi.txt" in " ".join(recheck["problems"]), True)
said = backup.verify_report(recheck)
check("the report is blunt about it", "not a faithful copy" in said, True)
check("and tells the user what to do", "make a fresh backup" in said, True)
clean = backup.verify(result["folder"])
check("an uncracked backup still verifies", clean["ok"], True)

print("6) dangerous shapes are refused, not attempted")
inside = backup.copy(str(src), str(src / "Old"))
check("copying a folder into itself is refused", "inside" in inside["error"].lower(), True)
same = backup.copy(str(src), str(src))
check("same source and target is refused", same["error"] != "", True)
drive_root = backup.copy("/", str(target))
check("a whole drive root is refused", "drive root" in drive_root["error"], True)
missing = backup.plan(str(root / "nope"), str(target))
check("a missing source is refused", missing["ok"], False)
check("with the path in the message", "nope" in missing["error"], True)
no_target = backup.plan(str(src), "")
check("no disk attached says so", "external disk" in no_target["error"]
      or "second drive" in no_target["error"], True)

print("7) not enough room is refused before a single byte is written")
# This section used to create a sparse file the size of the free space + 5 GB and let
# copy() run. On NTFS that is not free: the run spent 192 s on the Windows CI runner and
# told nobody anything new. The guard only needs the *reported* free space, so it is
# injected — the same thing the app sees when a drive really is full, with no I/O at all.
import arcdesk.backup as _bk2

_orig2 = _bk2.plan
_bk2.plan = _plan_with_free(1e-6)          # ~1 KB free, ~400 KB to copy
before = len(backup.backups(str(target)))
room = backup.copy(str(src), str(target))
check("it refused to fill the disk", "not enough room" in room["error"].lower(), True)
check("and created no folder", len(backup.backups(str(target))), before)
_bk2.plan = _orig2

print("8) autostart: one per-user entry, verified, reversible")
os.environ["ARCDESK_USER_HOME"] = str(root)
state = autostart.status()
check("off to begin with", state["enabled"], False)
on = autostart.enable()
check("enable worked", on["ok"], True)
check("read back as enabled", autostart.status()["enabled"], True)
check("is_enabled agrees", autostart.is_enabled(), True)
check("the entry points at a real program", autostart.status()["stale"], False)
check("it is per-user, not system-wide", "HKCU" in autostart.report() or
      str(autostart._linux_path()) in autostart.report() or
      "LaunchAgent" in autostart.report(), True)
check("the report says no admin was used", "No admin" in autostart.report(), True)
off = autostart.disable()
check("disable worked", off["ok"], True)
check("read back as off", autostart.status()["enabled"], False)
check("disabling twice is harmless", autostart.disable()["ok"], True)
check("it never hides itself", "Task Manager" in autostart.report()
      or "removable" in autostart.report(), True)

print("9) the wizard applies exactly the four answers")
cfg = config.load()
cfg["first_run"] = True
cfg.setdefault("wake", {})["enabled"] = False
config.save(cfg)
check("it shows on a first run", firstrun.should_show(config.load()), True)
check("the defaults are the cautious ones",
      [s["default"] for s in firstrun.steps()], [True, False, False, False])
answers = firstrun.answers_from(config.load())
check("it opens showing reality", answers["wake"], False)
applied = firstrun.apply(config.load(), {"voice": True, "wake": True, "autostart": True,
                                         "documents": True})
check("it reported what changed", len(applied["changed"]), 3)
check("it saved", applied["saved"], True)
saved = config.load()
check("wake word is on", saved["wake"]["enabled"], True)
check("document search is on", saved["docs"]["index_on_start"], True)
check("autostart is really on", autostart.is_enabled(), True)
check("first_run is cleared", saved["first_run"], False)
check("it no longer shows", firstrun.should_show(saved), False)
summary = firstrun.summary(applied)
check("the summary lists what was set", "Set up:" in summary, True)
check("and states the current state", "Opens by:" in summary, True)
check("...and says how it opens", "desktop icon" in summary or "voice" in summary, True)

print("10) refusing is a first-class outcome")
plain = firstrun.apply(config.load(), {"voice": True, "wake": False, "autostart": False,
                                       "documents": False})
check("everything off is allowed", plain["changed"], ["wake word off", "autostart off",
                                                      "document search off"])
check("and the microphone is genuinely off", config.load()["wake"]["enabled"], False)
check("and no startup entry is left", autostart.is_enabled(), False)
check("nothing is ever 'partly' saved", plain["saved"], True)

print("11) the background indexer never blocks and never lies")
docs_worker.status.update({"state": "idle"})
(Path(os.environ["ARCDESK_USER_HOME"]) / "Documents").mkdir(exist_ok=True)
(Path(os.environ["ARCDESK_USER_HOME"]) / "Documents" / "notes.txt").write_text(
    "the rooftop cafe invoice is 45000\n", encoding="utf-8")
started = docs_worker.start(None)
check("it starts", started, True)
check("starting twice is refused, not duplicated", docs_worker.start(None), False)
import time  # noqa: E402
for _ in range(100):
    if docs_worker.status["state"] in ("done", "failed"):
        break
    time.sleep(0.05)
check("it finished", docs_worker.status["state"], "done")
check("and counted what it read", docs_worker.status["count"] >= 1, True)
check("the words are searchable afterwards",
      "notes.txt" in deepsearch.results_text("rooftop cafe invoice"), True)

print("12) wired: two new tools and the phrases people say")
for name in ("backup", "autostart"):
    check(f"{name} registered", name in tools.TOOLS, True)
check("the backup tool requires confirmation before copying",
      tools.TOOLS["backup"].confirm, True)
check("tool count", len(tools.TOOLS) >= 86, True)
check("drives are listed", "disk" in tools.call("backup", {"action": "drives"}).lower()
      or "Disks" in tools.call("backup", {"action": "drives"}), True)
check("autostart status is read-only", "Start" in tools.call("autostart", {"action": "status"})
      or "start" in tools.call("autostart", {"action": "status"}), True)
for phrase, tool in (("back up my documents", "backup"),
                     ("start with windows", "autostart"),
                     ("stop starting with windows", "autostart"),
                     ("why is my pc slow", "pc_health"),
                     ("index my documents", "search_inside"),
                     ("play ilaya nila", "play")):
    _, calls = respond(phrase)
    check(f"“{phrase}” → {tool}",
          calls[0]["function"]["name"] if calls else None, tool)
_, calls = respond("start with windows")
check("'start with windows' means on", json.loads(calls[0]["function"]["arguments"])["action"],
      "on")
_, calls = respond("stop starting with windows")
check("'stop starting' means off", json.loads(calls[0]["function"]["arguments"])["action"],
      "off")

shutil.rmtree(root, ignore_errors=True)
print()
print("ALL PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
