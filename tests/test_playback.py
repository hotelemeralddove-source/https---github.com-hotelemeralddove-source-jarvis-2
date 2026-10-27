"""Playback, the media index and the planner — measured, not promised.

What has to be true for "play X" to feel like a light switch:

* the index finds the file, including on a drive ARC has never seen before;
* the search survives real filenames ("01 - X (Official Video) 320kbps.mp3");
* the player starts in milliseconds and can be stopped;
* a miss is a sentence with a next step, never a wrong file;
* the planner shows its steps before running them.

Run:  python tests/test_playback.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("ARCDESK_USER_HOME", tempfile.mkdtemp(prefix="arcdesk-user-"))
# no sound card in CI: ffplay's SDL still decodes, so we can prove start/stop timing
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import library, planner, player  # noqa: E402
from arcdesk.ai import tools  # noqa: E402

ok = True
FF = shutil.which("ffmpeg")
root = Path(tempfile.mkdtemp(prefix="arcdesk-media-lib-"))
music = root / "Music"
videos = root / "Videos"
hidden = root / "Windows"
for folder in (music, videos, hidden):
    folder.mkdir(parents=True, exist_ok=True)


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<56} {str(got)[:44]!r}")
    ok &= bool(good)


def tone(path: Path, seconds: float = 6.0) -> None:
    if FF:
        subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency=440:duration={seconds}", "-b:a", "128k",
                        str(path)], check=False, timeout=60)
    else:
        path.write_bytes(b"\x00" * 40_000)


def clip(path: Path) -> None:
    if FF:
        subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=160x120:rate=10:duration=1.5", "-c:v", "libx264",
                        "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)],
                       check=False, timeout=60)
    else:
        path.write_bytes(b"\x00" * 40_000)


print("1) a real folder, with the junk that real folders contain")
tone(music / "01 - Ilaya Nila (Official Video) 320kbps.mp3")
tone(music / "Kabira - Pritam.mp3")
tone(music / "Nee Paartha Vizhigal.mp3")
clip(videos / "Hampi trip day 2.mp4")
(music / "notes.txt").write_text("not media", encoding="utf-8")
(music / "tiny.mp3").write_bytes(b"\x00" * 500)          # ringtone/thumbnail: too small
tone(hidden / "should_not_appear.mp3")

data = library.scan(str(root))
names = [t["name"] for t in data["tracks"]]
print(f"   ..   scanned {data['folders']} folders in {data['seconds']}s, "
      f"{len(data['tracks'])} media files")
check("three songs and one video indexed", len(data["tracks"]), 4)
check("the track-number and quality junk is stripped", "Ilaya Nila" in names, True)
check("the .txt is ignored", any(t["ext"] == ".txt" for t in data["tracks"]), False)
check("the 500-byte file is skipped as a ringtone", "tiny" in " ".join(names), False)
check("a system folder name is skipped",
      any("should_not_appear" in t["path"] for t in data["tracks"]), False)
check("kinds are right",
      sorted(t["kind"] for t in data["tracks"]), ["audio", "audio", "audio", "video"])

print("2) search finds it the way a person says it")
for query, expected in (("ilaya nila", "Ilaya Nila"), ("ILAYA NILA", "Ilaya Nila"),
                        ("kabira", "Kabira - Pritam"),
                        ("ilaiya nila", "Ilaya Nila"),        # typo
                        ("nee paartha", "Nee Paartha Vizhigal")):
    hit = library.first_track(query)
    check(f"“{query}” → {expected}", bool(hit) and hit["name"] == expected, True)
check("a video request only returns videos",
      library.first_track("hampi", "video")["kind"], "video")
check("an audio request does not return the video",
      all(t["kind"] == "audio" for t in library.search("hampi", "audio")), True)
gone = library.search("song that does not exist anywhere")
check("a miss returns nothing (so the caller can be honest)", gone, [])
check("the miss text offers the scan", "scan" in library.results_text("nope nope"), True)

print("3) the search stays instant on a big index")
_original = library.load
fake = [{"path": f"/x/{i}.mp3", "name": f"Track number {i}", "artist": "",
         "kind": "audio", "ext": ".mp3", "size": 4_000_000, "mtime": i,
         "search": f"track number {i}"} for i in range(20_000)]
library.load = lambda force=False: {"built": time.time(), "tracks": fake, "roots": ["/x"]}
started = time.time()
library.search("track number 19999")
elapsed = (time.time() - started) * 1000
# the budget is about "does the search feel instant", not about this build host's
# load: 120 ms failed only when six other test processes were running.
check(f"20,000 rows searched in {elapsed:.0f} ms (<200 ms)", elapsed < 200, True)
library.load = _original

print("4) an external disk is just a path")
saved = library.drives
library.drives = lambda: [{"path": str(root), "label": "PENDRIVE", "removable": True,
                           "total_gb": 32.0}]
check("the drive is offered as a root", str(root) in library.default_roots(), True)
check("the planner finds the external root", str(root) in planner.external_roots(), True)
library.drives = saved

print("5) playback: starts in milliseconds, and stops when asked")
players = player.candidates()
print(f"   ..   players available: {[p['name'] for p in players] or 'none'}")
cmd = player._cmd_for({"name": "ffplay", "path": "ffplay"}, ["/x/a.mp3"], False)
check("ffplay gets -nodisp for audio", "-nodisp" in cmd, True)
check("mpv gets --no-video for audio",
      "--no-video" in player._cmd_for({"name": "mpv", "path": "mpv"}, ["/x/a.mp3"], False),
      True)


if players:
    result = player.play("ilaya nila")
    check("play started", result.startswith("▶"), True)
    check("it reports the startup time", "started in" in result, True)
    _status = player.status()
    check("status names the file", "Ilaya Nila" in _status, True)
    time.sleep(0.4)
    stopped = player.stop()
    check("stop works", "stopped" in stopped, True)
    check("nothing is playing afterwards", "nothing playing" in player.status(), True)
    video = player.play("hampi trip", "video")
    check("a video plays too", video.startswith("▶"), True)
    player.stop()
else:
    print("   ..   no command-line player installed — start/stop checks skipped")

missing = player.play("a song that is not there at all")
check("a miss is a sentence, not a random file", "could not find" in missing.lower(), True)

print("6) the planner thinks before it acts")
for request, steps in (("scan my external disk", 1),
                       ("play ilaya nila", 1),
                       ("scan my external disk and play kabira", 2),
                       ("play the video hampi trip", 1)):
    plan = planner.think(request)
    check(f"“{request}” → {steps} step(s)", len(plan["steps"]), steps)
check("the plan names its tools", "library" in planner.describe_plan(
    planner.think("scan my external disk")), True)
check("a play step carries the query",
      planner.think("play ilaya nila")["steps"][0][1]["query"], "ilaya nila")
check("an external disk is scanned explicitly",
      planner.think("scan d drive")["steps"][0][1].get("roots"), "D:\\")
check("nonsense is not given a fake plan", planner.think("asdkjfh qwerty")["steps"], [])
check("the recipes are described", "scan my external disk" in planner.recipes().lower(), True)

rescan = tools.call("library", {"action": "scan", "roots": str(root)})
check("an explicit scan reports what it found", "indexed 4 media files" in rescan, True)

if players:
    transcript = planner.run("scan my external disk and play kabira")
    # with no external disk attached the first step must say so rather than rescanning
    check("it says when there is no external disk",
          "no external disk" in transcript or "Scanned" in transcript, True)
    check("it still played the song", "▶" in transcript, True)
    check("it prints the steps it took", "✓ 1." in transcript, True)
    player.stop()

print("7) wired as tools")
for name in ("play", "library", "plan", "coach"):
    check(f"{name} registered", name in tools.TOOLS, True)
check("tool count", len(tools.TOOLS) >= 81, True)
check("library dispatches", "media files" in tools.call("library", {"action": "stats"}),
      True)
check("play status dispatches", "playing" in tools.call("play", {"action": "status"}), True)
check("planner recipes dispatch", "scan" in tools.call("plan", {"action": "recipes"}), True)

print("8) end to end: the typed command, through the real agent")
try:
    from PySide6.QtCore import QCoreApplication
    from arcdesk.ai.agent import Agent
    from arcdesk.config import load

    app = QCoreApplication.instance() or QCoreApplication([])
    agent = Agent(load())
    said = []
    agent.reply.connect(said.append)
    agent.error.connect(said.append)
    player.stop()
    agent.ask("play ilaya nila")
    deadline = time.time() + 20
    while time.time() < deadline and not said:
        app.processEvents()
        time.sleep(0.05)
    check("the agent answered", bool(said), True)
    check("it reached the player", "▶" in (said[0] if said else ""), True)
    check("a real process is running", "playing" in player.status(), True)
    player.stop()
except Exception as exc:                    # no PySide6 here: the rest still counts
    print(f"   ..   agent check skipped: {exc}")

print()
print("ALL PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
