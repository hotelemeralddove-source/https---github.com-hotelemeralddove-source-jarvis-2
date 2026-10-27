"""Carrying ARC to a second laptop — with the right things, and not the others.

The question: *"intha application-a vera laptop-la install pana mudiyuma? anga vera
voice-la kooda work aagura mathiri set panna mudiyuma?"*

Two answers, both tested here:

  * **yes, data moves** — `tools/move.py pack` / `unpack` carries settings, vault and the
    clone reference, and keeps the projects of both machines when merging;
  * **yes, another voice** — the voice lock is per machine by design, so laptop B
    enrols its own person; nothing of laptop A's fingerprint travels.

And one honest limit this test *encodes* rather than hides: **the .exe is not built
here.** PyInstaller does not cross-compile, so the program comes from a Windows
machine; `move.py` only ever moves data.

Run:  python tests/test_move.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(ROOT))

BASE = Path(tempfile.mkdtemp(prefix="arcdesk-move-"))
os.environ["ARCDESK_HOME"] = str(BASE / "laptopA")

from arcdesk import clone, config, vault, voiceid  # noqa: E402
import move  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:34]!r}")
    ok &= bool(good)


def make_laptop(name: str) -> None:
    """Switch the process to another machine's data folder."""
    os.environ["ARCDESK_HOME"] = str(BASE / name)


def seed() -> None:
    cfg = config.load()
    cfg.setdefault("ai", {})["api_key"] = "sk-do-not-travel"
    cfg.setdefault("weather", {})["city"] = "Belagavi"
    config.save(cfg)
    vault.create("Elephant project", "drawing vs photo")
    vault.checkpoint("asked for a real elephant photo")
    home = config.data_dir()
    (home / "voice").mkdir(exist_ok=True)
    (home / "voice" / "reference.wav").write_bytes(b"RIFF" + b"\x00" * 200)
    (home / "voice" / "reference.txt").write_text("vanakkam macha\n", encoding="utf-8")
    voiceid._save({"me": {"vector": [1.0, 0.0], "samples": 3,
                          "threshold": 0.62, "created": "today"}})
    (home / "models").mkdir(exist_ok=True)
    (home / "models" / "big.onnx").write_bytes(b"x" * 4096)
    (home / "logs").mkdir(exist_ok=True)
    (home / "logs" / "app.log").write_text("machine A noise", encoding="utf-8")
    (home / "profile.json").write_text('{"name": "Machi"}', encoding="utf-8")


print("\n1) check lists what travels and what cannot")
plan = move.collect()
print("   (laptop A has not been seeded yet)")
seed()
plan = move.collect()
names = [n for _p, n in plan["items"]]
check("vault travels", "vault" in names)
check("voice reference travels", "voice" in names)
check("personal profile travels", "profile.json" in names)
check("models are not packed", "models" in plan["skipped"])
check("voice lock is left behind", "voiceid" in plan["skipped"])
check("logs are not packed", "logs" in plan["skipped"])
check("media is opt-in", "photos" not in names)

print("\n2) pack strips API keys by default")
target = BASE / "carry.zip"
got = move.pack(str(target))
check("packed", got["ok"])
check("one file", target.exists())
check("size is reported", bool(got["total"]))
check("key removed", "ai.api_key" in got["removed"])

print("\n3) unpack on laptop B restores the work, not the machine")
make_laptop("laptopB")
got = move.unpack(str(target))
check("unpacked", got["ok"])
check("settings arrived", config.load()["weather"]["city"], "Belagavi")
check("the API key did NOT travel", config.load()["ai"]["api_key"], "")
check("the project arrived", [p["name"] for p in vault.projects()], ["Elephant project"])
resumed = vault.resume()
check("progress arrived", resumed["ok"] and resumed["checkpoints"] >= 1,
      True)
check("clone reference arrived", clone.transcript(), "vanakkam macha")
check("no fingerprint arrived", voiceid.profiles(), {})
check("no models arrived", (config.data_dir() / "models").exists(), False)
check("no logs arrived", (config.data_dir() / "logs").exists(), False)

print("\n4) laptop B can enrol a DIFFERENT voice without touching laptop A")
voiceid.available = lambda: (True, "")
voiceid.embed = lambda p: [1.0, 0.0] if "b" in Path(p).stem else [0.0, 1.0]
for n in ("rb1", "rb2", "rb3"):
    (config.data_dir() / f"{n}.wav").write_bytes(b"\x00" * 40)
enrol = voiceid.enroll("wife-on-B", [str(config.data_dir() / f"rb{i}.wav")
                                     for i in (1, 2, 3)])
check("enrolled on laptop B", enrol["ok"])
check("only B's person is there", sorted(voiceid.profiles()), ["wife-on-B"])
make_laptop("laptopA")
check("laptop A still has its own person", sorted(voiceid.profiles()), ["me"])
make_laptop("laptopB")

print("\n5) unpacking twice does not silently overwrite")
again = move.unpack(str(target))
check("refused", again["ok"], False)
check("and says why", "already has settings" in again["message"], True)
check("nothing was destroyed", config.load()["weather"]["city"], "Belagavi")

print("\n6) --merge keeps the projects of both machines")
make_laptop("laptopC")
vault.create("Project made on C", "local work")
merged = move.unpack(str(target), merge=True)
check("merged", merged["ok"])
check("both projects present",
      sorted(p["name"] for p in vault.projects()), ["Elephant project", "Project made on C"])
check("the local one was not overwritten",
      [p["name"] for p in vault.projects()].count("Project made on C"), 1)
check("merge reports what it added", any("elephant" in r.lower() for r in merged["restored"]),
      True)

print("\n7) --force replaces, and --with-keys really keeps the key")
make_laptop("laptopD")
vault.create("Throwaway", "x")
forced = move.unpack(str(target), force=True)
check("forced", forced["ok"])
check("old project gone", [p["name"] for p in vault.projects()], ["Elephant project"])
cfg = config.load()
cfg.setdefault("ai", {})["api_key"] = "sk-keep-me"
config.save(cfg)
keyed = move.pack(str(BASE / "carry-keys.zip"), with_keys=True)
check("keys kept when asked", keyed["removed"], [])
make_laptop("laptopE")
move.unpack(str(BASE / "carry-keys.zip"))
check("key present on E", config.load()["ai"]["api_key"], "sk-keep-me")

print("\n8) a .zip round-trips as a folder too")
move.pack(str(BASE / "carry-folder"))
check("folder package exists", (BASE / "carry-folder").is_dir())
check("manifest written", (BASE / "carry-folder" / move.MANIFEST).exists())
manifest = json.loads((BASE / "carry-folder" / move.MANIFEST).read_text(encoding="utf-8"))
check("manifest names the version", manifest["pack_version"], move.PACK_VERSION)
check("manifest lists the key removal", "ai.api_key" in manifest["api_keys_removed"])
check("zip really is a zip", zipfile.is_zipfile(target), True)

print("\n9) the honest limit is written down, not hoped for")
src = Path(move.__file__).read_text(encoding="utf-8")
check("move.py says the exe is built on Windows", "cross-compile" in src, True)
check("move.py says voice lock is per machine", "per machine" in src, True)

print("\n" + ("ALL PASS" if ok else "SOMETHING FAILED"))
sys.exit(0 if ok else 1)
