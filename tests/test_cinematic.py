"""Cinematic cues and a companion voice — the sound of the thing, and the words

    python tests/test_cinematic.py

Two requests, tested together because they fire at the same moments:

  * *"jarvis open aagi magic mode begin aagum pothu, close aagum pothu athuku match aagura
    mathiri fx beats, task process aagum pothu oru beat, completed na oru beat"*
  * *"'hey jarvis' nu nan solum pothu reply voice la 'hi commander' nu jarvis solanum,
    'bye' solum pothu 'thank you commander' sollanum, task assign pana athuku related ah
    pesanum"*

What is asserted, and why each one is worth a test:

  1. the cues are **generated, not downloaded** — small files, right lengths, made once;
  2. playing a cue **never blocks and never raises** — no audio device is a normal
     machine, and a missing cue must not be why a wake word fails;
  3. the same cue cannot machine-gun (one task with four tools is not a pinball table);
  4. the volume is part of the cache key, so moving the slider regenerates nothing;
  5. every companion line, including the two exact ones that were asked for;
  6. the acknowledgement is **about the task** ("Opening Notepad") not "OK";
  7. the greeting is spoken through the **reply voice** (the cloned one), not a beep;
  8. the farewell happens **before** the app goes away, or it sounds like a crash.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import wave

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-cinematic-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])

from arcdesk import companion_voice, config, identity, sfx  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:44]!r}")
    ok &= bool(good)


print("1) seven cues, generated in the app — nothing to download")
names = set(sfx.CUES)
check("wake, magic begin/end, task start/done/failed, click",
      names, {"wake", "magic_begin", "magic_end", "task_start", "task_done",
              "task_failed", "click"})
started = time.monotonic()
made = sfx.ensure_all(0.55)
took = time.monotonic() - started
check("all seven were written", len([p for p in made.values() if p]), 7)
check("…quickly enough to do on first launch", took < 20.0, True)
total = sum(Path(p).stat().st_size for p in made.values())
check("the whole set is tiny (no download, no licence)", total < 400 * 1024, True)
for name, path in made.items():
    with wave.open(path) as w:
        dur = w.getnframes() / w.getframerate()
        fmt = (w.getnchannels(), w.getsampwidth(), w.getframerate())
    check(f"{name}: {dur:.2f} s, mono 16-bit 22 kHz", fmt, (1, 2, sfx.RATE))
    check(f"{name}: short enough not to become annoying", dur <= 1.6, True)
check("they live in the app's own folder", str(sfx.sfx_dir()).endswith("sfx"), True)

print("\n2) playing never blocks and never raises")
played: list[str] = []
real_play_async = sfx._play_async
sfx._play_async = lambda p: (played.append(p), True)[1]
t0 = time.monotonic()
check("play() returns immediately", sfx.play("magic_begin", {"sfx": {"enabled": True,
                                                                   "volume": 0.5}}), True)
check("…in well under a frame", (time.monotonic() - t0) < 0.05, True)
time.sleep(0.35)
check("…and the cue really reached the player", len(played) >= 1, True)
sfx._play_async = real_play_async


def boom(_p: str) -> bool:
    raise RuntimeError("no such audio device")


sfx._play_async = boom
check("a broken audio device does not raise", sfx.play("wake", {"sfx": {"enabled": True}}),
      True)
time.sleep(0.15)
sfx._play_async = real_play_async
check("switched off means silent", sfx.play("wake", {"sfx": {"enabled": False}}), False)
check("volume 0 means silent", sfx.play("wake", {"sfx": {"enabled": True,
                                                        "volume": 0.0}}), False)

print("\n3) no machine-gunning, and the volume is in the cache key")
sfx._LAST.clear()
fired = [sfx.play("task_done", {}, min_gap=5.0) for _ in range(3)]
check("three requests in a row play one cue", fired.count(True), 1)
check("a different volume is a different file",
      sfx.cue_path("task_done", 0.2) != sfx.cue_path("task_done", 0.9), True)
check("a change of 4% shares the cached file (no regeneration churn)",
      sfx.cue_path("task_done", 0.51) == sfx.cue_path("task_done", 0.54), True)

print("\n4) the companion lines — the two that were asked for, word for word")
cfg = config.load()
check("the name it speaks is JARVIS", identity.name(cfg), "JARVIS")
check("“hey jarvis” is answered with exactly this", companion_voice.greeting(cfg),
      "Hi commander.")
check("“bye” is answered with exactly this", companion_voice.farewell(cfg),
      "Thank you, commander.")
check("a slow task says it is still working", "Still on it" in companion_voice.progress(cfg),
      True)
check("finishing has a line", companion_voice.done(cfg), "Done, commander.")
check("failing has an honest one", companion_voice.done(cfg, ok=False),
      "That did not work, commander.")
check("every line ends like a sentence", companion_voice.greeting(cfg).endswith("."), True)
check("they are short (a companion, not a narrator)",
      max(len(v) for v in companion_voice.phrases(cfg).values()) < 60, True)

print("\n5) the acknowledgement is about the task, not 'OK'")
for said, expect in (
        ("open notepad", "Opening Notepad"),
        ("close chrome", "Closing Chrome"),
        ("open notepad and tell me my cpu", "Opening Notepad"),
        ("what is my cpu usage", "Checking the machine"),
        ("set a timer for 10 minutes", "Setting that up"),
        ("take a screenshot", "Capturing the screen"),
        ("search for cheap flights", "Searching"),
):
    got = companion_voice.ack(cfg, said)
    check(f"“{said[:28]}” → {expect}", got.startswith(expect), True)
check("an unrecognised request still has an answer",
      companion_voice.ack(cfg, "do the thing we talked about"), "On it, commander.")
check("a question is not pretended to be a command",
      companion_voice.ack(cfg, "why is the fan loud?"), "Let me think about that, commander.")

print("\n6) the honourific is a setting, and the whole thing can go quiet")
cfg2 = {"companion": {"enabled": True, "honorific": "sir"}}
check("calls you sir when asked", companion_voice.greeting(cfg2), "Hi sir.")
check("…and in every line", companion_voice.farewell(cfg2), "Thank you, sir.")
check("an empty honourific falls back", companion_voice.honorific(
    {"companion": {"honorific": "  "}}), "commander")
check("switched off means no lines at all",
      companion_voice.enabled({"companion": {"enabled": False}}), False)

print("\n7) it is spoken through the reply voice, at the right moments")
from arcdesk import activity  # noqa: E402
from arcdesk.widgets.window import MainWindow  # noqa: E402

activity.reset()
win = MainWindow(config.load())
win.show()
app.processEvents()
said: list[str] = []
win.voice.speak = lambda text, **kw: said.append(text)

win.greet()
# word for word, every time. A wake word that answers differently each morning is a
# slot machine, not a companion — and "hi commander" is the line that was asked for.
check("the wake word greets in the reply voice, word for word", said[-1], "Hi commander.")
win._pending_request = "open notepad"
activity.activity().begin("open notepad")
win._say_ack()
check("a slow task gets a task-related acknowledgement", said[-1], "Opening Notepad, commander.")
activity.activity().finish(ok=True)
win.agent.thinking.emit(False)
app.processEvents()
check("nothing extra is said on completion by default", said[-1],
      "Opening Notepad, commander.")

# the farewell must come BEFORE the app leaves
order: list[str] = []
win.voice.speak = lambda text, **kw: order.append("said:" + text)
win._apply_bye_action = lambda: order.append("closed")
win.farewell_and_close()
check("the sentence starts before the app closes", order, ["said:Thank you, commander."])
deadline = time.monotonic() + 3.0
while time.monotonic() < deadline and len(order) < 2:
    app.processEvents()
    time.sleep(0.02)
check("…and the close still happens, just after it",
      order[-1:] == ["closed"], True)

print("\n8) the switches are in Settings, and the cues are named there")
settings_src = (ROOT / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
check("a checkbox for the cues", "sfx_on" in settings_src, True)
check("a volume slider", "sfx_volume" in settings_src, True)
check("a checkbox for the companion voice", "companion_on" in settings_src, True)
check("the honourific is editable", "honorific" in settings_src, True)
check("the settings are saved, not just drawn",
      'self.cfg.setdefault("sfx"' in settings_src, True)
check("…both of them", 'self.cfg.setdefault("companion"' in settings_src, True)
window_src = (ROOT / "arcdesk" / "widgets" / "window.py").read_text(encoding="utf-8")
for cue in ("magic_begin", "magic_end", "task_start", "task_done", "wake"):
    check(f"the app plays “{cue}” at the right moment", f'sfx.play("{cue}"' in window_src, True)

print("\n9) opening by hand is not silent")
# The defect this section exists for: launching the book by pressing the magic button
# (or any road that is not the wake word) never passed through awaken(), so there was
# no opening beat and no hello — the app opened in silence.
cues: list[str] = []
real_play = sfx.play
sfx.play = lambda name, cfg=None, **kw: (cues.append(name), False)[1]
try:
    win2 = MainWindow(config.load())
    win2.show()
    app.processEvents()
    said2: list[str] = []
    win2.voice.speak = lambda text, **kw: said2.append(text)
    win2.enter_magic()
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and not said2:
        app.processEvents()
        time.sleep(0.02)
    check("pressing the magic button has its own beat", "magic_begin" in cues, True)
    check("…and it says hello, unprompted", said2[:1], ["Hi commander."])
    before = cues.count("magic_begin")
    win2._cinematic_open()            # the other door, a moment later
    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    check("two doors, one opening: it does not stutter", cues.count("magic_begin"), before)
    check("…and one hello", len(said2), 1)
    win2.shutdown()
finally:
    sfx.play = real_play

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
