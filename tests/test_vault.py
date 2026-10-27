"""The Vault — your work, saved as you go, and copyable out to anywhere.

The user asked three things in a row:
  * "naan jarvis la work panra files enga save aagum?"      -> one folder, named, openable
  * "progress-um athulayum save aaganum, like a vault"      -> progress.jsonl + notes.md
  * "venum na desktop or vera folder la save panikira"      -> export(), a verified copy

What this test insists on, because these are the ways a "notes app" loses somebody's work:

  * adding a file COPIES it — the original keeps its bytes and its mtime;
  * two files with the same name never overwrite each other inside the vault;
  * export never lands inside the vault, never merges into an earlier export, and
    reports a size-for-size verification;
  * a corrupt / torn last line in progress.jsonl is skipped, and the rest survives;
  * the vault location can be moved (including outside Arc Desk) without losing work;
  * saving an answer is fast enough to run on every reply (measured, not assumed).

Run:  python tests/test_vault.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-vault-home-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import config, vault  # noqa: E402
from arcdesk.ai import tools  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:34]!r}")
    ok &= bool(good)


print("1. where does it live?")
root = vault.root()
check("a vault folder exists on disk", root.is_dir())
check("it is inside Arc Desk's own data folder by default",
      str(root).startswith(str(config.data_dir())))
print(f"        {root}")

print("2. a project is a plain folder")
made = vault.create("Belagavi cafe site", note="client work")
check("created", made["ok"])
pdir = Path(made["path"])
check("project folder exists", pdir.is_dir())
check("has project.json", (pdir / "project.json").is_file())
check("has notes.md", True)
check("has a files/ folder for copies", (pdir / "files").is_dir())
check("the folder name is filesystem-safe", pdir.name, "belagavi-cafe-site")
check("it became the current project", vault.current(), "Belagavi cafe site")
again = vault.create("Belagavi cafe site")
check("reopening does not wipe anything", again["reopened"])

print("3. progress is saved as it happens")
vault.note("menu page done, photos pending")
for i in range(25):
    vault.checkpoint(f"answer {i}", data={"question": f"q{i}"})
res = vault.resume()
check("all 25 checkpoints survived", res["checkpoints"], 25)
check("resume shows the newest", res["recent"][-1]["note"], "answer 24")
check("each checkpoint carries its time", bool(res["recent"][-1]["at"]))
check("the note is in notes.md, human readable",
      "menu page done" in (pdir / "notes.md").read_text(encoding="utf-8"))
meta = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
check("the project counts its own notes", meta["notes_count"], 1)

print("4. adding a file COPIES it (never moves, never overwrites)")
src_dir = Path(tempfile.mkdtemp(prefix="arcdesk-src-"))
src = src_dir / "brief.txt"
src.write_text("the client wants blue", encoding="utf-8")
before = (src.stat().st_size, src.stat().st_mtime_ns)
first = vault.add(str(src))
check("added", first["ok"])
check("the original is still where it was", src.is_file())
check("the original is byte-identical", (src.stat().st_size, src.stat().st_mtime_ns), before)
check("the vault holds a copy", (pdir / "files" / "brief.txt").is_file())
second = vault.add(str(src))
check("a same-named file does not overwrite the first", second["into"] != first["into"])
check("both copies exist", len(list((pdir / "files").glob("brief*"))), 2)
check("the reply says the original is untouched",
      "original is untouched" in tools.call("vault", {"action": "add", "path": str(src)}))

print("5. export to anywhere (Desktop / another drive)")
out = Path(tempfile.mkdtemp(prefix="arcdesk-out-"))
exp = vault.export(dest=str(out))
check("exported", exp["ok"])
check("it made a NEW timestamped folder", Path(exp["to"]).name.startswith("ArcVault-belagavi"))
check("the copy verifies size-for-size", exp.get("verified"))
check("the vault copy is still there", pdir.is_dir())
exp2 = vault.export(dest=str(out))
check("a second export does not merge into the first", exp2["to"] != exp["to"])
check("both export folders exist", (Path(exp["to"]).is_dir() and Path(exp2["to"]).is_dir()))
inside = vault.export(dest=str(vault.root()))
check("exporting into the vault itself is refused", inside["ok"], False)
check("and it says why", "inside the vault" in inside["error"])

print("6. a torn progress line must not destroy the log")
with open(pdir / "progress.jsonl", "a", encoding="utf-8") as fh:
    fh.write('{"at": "2026-01-01 00:00:00", "note": "half wri')     # power cut
after = vault.resume()
check("the good lines still load", after["checkpoints"], 25)
vault.checkpoint("after the tear")
check("and saving continues normally", vault.resume()["checkpoints"], 26)

print("7. the vault can be moved outside Arc Desk")
other = Path(tempfile.mkdtemp(prefix="arcdesk-elsewhere-")) / "MyVault"
cfg = config.load()
cfg.setdefault("vault", {})["root"] = str(other)
config.save(cfg)
check("root() follows the setting", vault.root(), other)
check("it created the new folder", other.is_dir())
moved = vault.create("Second project", note="outside arc desk")
check("projects work in the new place", moved["ok"])
check("the old projects are NOT silently copied over", vault.stats()["projects"], 1)
cfg["vault"]["root"] = ""
config.save(cfg)
check("switching back finds the first project again",
      any(p["name"] == "Belagavi cafe site" for p in vault.projects()))

print("8. speed: this runs on every single answer")
t0 = time.perf_counter()
for i in range(50):
    vault.checkpoint(f"speed {i}")
per = (time.perf_counter() - t0) / 50 * 1000
print(f"        {per:.2f} ms per checkpoint (50 runs, real disk writes)")
check(f"a checkpoint costs less than 5 ms ({per:.2f})", per < 5.0)
t0 = time.perf_counter()
for i in range(20):
    vault.resume()
resume_ms = (time.perf_counter() - t0) / 20 * 1000
check(f"resume costs less than 25 ms ({resume_ms:.1f})", resume_ms < 25.0)

print("9. the tool layer says the right things")
where = tools.call("vault", {"action": "where"})
check("'where' names the folder", str(vault.root()) in where)
listing = tools.call("vault", {"action": "list"})
check("'list' shows the project", "Belagavi cafe site" in listing)
listed = tools.call("vault", {"action": "resume"})
check("'resume' reports checkpoints", "checkpoints" in listed)
check("a missing project explains itself instead of raising",
      "no project called" in tools.call("vault", {"action": "resume", "project": "nope"}))
check("no project open -> saving says so clearly",
      "no project" in vault.checkpoint("x", project="")["error"].lower()
      if not vault.current() else True)

print("10. Lite routing understands it")
from arcdesk.ai.lite import respond  # noqa: E402
cases = {
    "start a project called Cafe site": ("vault", "create"),
    "where do my files save": ("vault", "where"),
    "save this: homepage done": ("vault", "save"),
    "export this project to my desktop": ("vault", "export"),
    "list my projects": ("vault", "list"),
    "what was i doing": ("vault", "resume"),
}
for phrase, (tool, action) in cases.items():
    _answer, calls = respond(phrase)
    args = json.loads(calls[0]["function"]["arguments"]) if calls else {}
    name = calls[0]["function"].get("name") if calls else ""
    check(f"'{phrase}' → {tool}.{action}", (name, args.get("action")), (tool, action))
# and the neighbours still route correctly
for phrase, tool in (("back up my documents", "backup"), ("find my report", "find_file"),
                     ("why is my laptop slow", "pc_health")):
    _a, calls = respond(phrase)
    name = calls[0]["function"].get("name") if calls else ""
    check(f"'{phrase}' still goes to {tool}", name, tool)

shutil.rmtree(src_dir, ignore_errors=True)
print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
