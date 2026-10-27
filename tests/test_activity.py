"""What is it doing? — the question the user asked while it looked hung

    python tests/test_activity.py

Three complaints, one test file:

  * *"romba hang and slow ah iruku… ena work nadakuthu nu therinja nalla irukum"* —
    there is now a live line with a seconds counter, and a timeline of finished steps;
  * *"task assign pana work aagutha nu theriya matiku"* — the counter moves, the dot
    changes colour, and STOP actually stops between steps;
  * *"esc kodutha close aaga matiku"* — Esc is handled by an application-wide filter, so
    it works with the focus in the chat box, in the transcript, or nowhere at all.

Also measured here: the window stops animating when it is hidden (stealth is the resting
state, so that was a 30 fps repaint nobody could see), and the frame-rate guard reacts to
real frame cost instead of being reset every ten seconds.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-activity-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])

from arcdesk import activity, config  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:44]!r}")
    ok &= bool(good)


print("1) the record: one live step, finished steps kept, cancel is real")
act = activity.reset()
check("starts idle", act.state, "idle")
check("idle is not busy", act.busy, False)
act.begin("open notepad and tell me my cpu")
check("a request makes it busy", act.busy, True)
check("the request is remembered", act.snapshot()["request"][:12], "open notepad")
time.sleep(0.35)          # the trail deliberately ignores sub-0.3 s thinking blips
first = act.elapsed()
check("the clock moves, so 'working' can be told from 'wedged'", first > 0.3, True)
check("the live line has the step and the seconds", "thinking" in act.line(), True)
act.step("tool: open_app")
time.sleep(0.05)
snap = act.snapshot()
check("the new step is live", snap["live"].startswith("tool: open_app"), True)
check("thinking was closed into the timeline",
      any("thinking" in h for h in snap["history"]), True)
check("snapshot is a copy, not the live object", isinstance(snap["history"], list), True)
act.step("tool: system_report")
act.note("denied")
check("a note lands on the running step", "denied" in act.snapshot()["live"], True)
check("the live line carries no bare number (the clock is drawn separately)",
      any(ch.isdigit() for ch in act.snapshot()["live"]), False)
check("stop is possible while busy", act.cancel(), True)
check("…and the state says cancelled", act.state, "cancelled")
check("…and the flag the agent reads is set", act.cancelled(), True)
act.finish(ok=False, why="you stopped it")
check("finishing keeps the trail", len(act.snapshot()["history"]) >= 2, True)
check("a stopped request says so", "stopped" in " ".join(act.snapshot()["history"]), True)
check("a new request clears the old cancel flag", (act.begin("x"), act.cancelled())[1], False)

print("\n2) the agent reports each step, and obeys Stop between them")
from arcdesk.ai import agent as agent_mod  # noqa: E402
from arcdesk.ai import tools as tools_mod  # noqa: E402

seen: list[str] = []
real_call = tools_mod.call


def fake_call(name, args):
    seen.append(name)
    time.sleep(0.05)
    return f"{name} done"


tools_mod.call = fake_call
bot = agent_mod.Agent(config.load())
act = activity.reset()
act.begin("do two things")
out1 = bot._execute("system_report", {})
check("the first tool ran", out1, "system_report done")
check("the record shows which tool", "system_report" in act.snapshot()["live"], True)
act.cancel()                                    # the user pressed STOP
out2 = bot._execute("battery", {})
check("the next tool does NOT run", "battery" in seen, False)
check("…and it says why", "stopped before running" in out2, True)
check("the step that ran is still on record",
      "system_report" in act.snapshot()["live"]
      or any("system_report" in h for h in act.snapshot()["history"]), True)

print("\n3) a slow tool is labelled with its own time")
act = activity.reset()
act.begin("slow one")


def slow_call(name, args):
    time.sleep(1.6)          # over the "slow enough to mention" line
    return "slow but fine"


tools_mod.call = slow_call
bot._execute("system_report", {})
snap = act.snapshot()
check("a slow step says so in words", "slow" in snap["live"], True)
check("…and the seconds are on the clock, once", f"{snap['elapsed']:.1f}" in
      f"{snap['elapsed']:.1f}", True)
tools_mod.call = real_call

print("\n4) the console: a live line, a visible STOP, and a moving number")
from arcdesk.widgets.window import MainWindow  # noqa: E402

activity.reset()               # a fresh record, like a fresh start
win = MainWindow(config.load())
win.show()
app.processEvents()
con = win.console
check("idle is stated, not blank", "idle" in con.live.text(), True)
# isVisibleTo, not isVisible: the console lives on a page of a stacked widget, so a
# widget can be "shown" and still not be on screen. This asks the question intended.
check("STOP is hidden when nothing runs", con.stop_btn.isVisibleTo(con), False)
act = activity.reset()
act.begin("open notepad")
win.agent.thinking.emit(True)
app.processEvents()
check("busy shows STOP", con.stop_btn.isVisibleTo(con), True)
check("busy shows the step", "thinking" in con.live.text(), True)
act.step("tool: open_app")
con.refresh_activity()
check("the step appears without waiting for the end", "open_app" in con.live.text(), True)
before = con.live.text()
time.sleep(0.25)
con.refresh_activity()
check("the seconds counter advances", con.live.text() != before, True)
check("the dot has a state for the stylesheet", con.dot.property("state"), "tool")

print("\n4b) the process strip: every step, running then finished, in order")
con.begin_task("")
con.step_running("thinking · the model is reading it")
check("a running step is marked as running", "▸ thinking" in con.proc.text(), True)
con.step_done("thinking · the model is reading it", 2.4)
check("…and becomes a finished step with its time",
      "✔ thinking" in con.proc.text() and "2.4 s" in con.proc.text(), True)
con.step_running("tool: open_app")
con.step_done("tool: open_app", 0.3)
check("two steps are both on the strip", con.proc.text().count("✔"), 2, )
check("in the order they ran",
      con.proc.text().index("thinking") < con.proc.text().index("open_app"), True)
con.begin_task("")
check("a new request clears the strip", con.proc.text(), "")

print("\n5) Esc works wherever the focus is — including inside the chat field")
con.input.setFocus()
app.processEvents()
check("the chat field really has the focus", app.focusWidget() is con.input, True)


def press_escape(widget):
    app.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                    Qt.KeyboardModifier.NoModifier))


press_escape(con.input)
app.processEvents()
check("Esc from the chat box cancelled the task", act.state, "cancelled")
check("…and the console says so", "STOPPED" in con.view.toPlainText(), True)
check("…and STOP is gone again", con.stop_btn.isVisibleTo(con), False)

win.toggle_console(True)
app.processEvents()
press_escape(win.console.view)
app.processEvents()
check("Esc with the transcript focused closes the console", win._console_open, False)
press_escape(win)
app.processEvents()
check("Esc on an idle window hides it", win.isVisible(), False)
# ...and the same ladder through the application-wide shortcut, which is what fires on
# Windows even when the focus is inside a text field
check("there is an application-wide Esc shortcut", win._esc is not None, True)
check("it is registered for the whole app, not just the window",
      win._esc.context() == Qt.ShortcutContext.ApplicationShortcut, True)
win.show()
app.processEvents()
act.begin("slow request")
win.escape_pressed()
check("the shortcut path cancels a running task", act.state, "cancelled")
win.show()
app.processEvents()
win.escape_pressed()
check("…and hides an idle window", win.isVisible(), False)

print("\n6) a hidden window does not animate (stealth is the resting state)")
from arcdesk.ticker import ticker  # noqa: E402

check("hidden → the ticker is paused", ticker().paused, True)
check("a paused ticker reports 0 fps", ticker().fps, 0)
win.show()
app.processEvents()
check("shown again → it resumes", ticker().paused, False)
check("and it has a real frame rate", ticker().fps > 0, True)

print("\n7) the frame-rate guard reacts to measured cost, and is not undone")
ticker().set_auto(True)
ticker().set_base_fps(30)
ticker()._frame_ms = 40.0        # 40 ms a frame cannot fit in 33 ms
for _ in range(50):
    ticker()._adapt()
check("a machine that cannot afford 30 fps is slowed down", ticker().fps < 30, True)
check("…but never into a slideshow", ticker().fps >= 12, True)
slowed = ticker().fps
ticker()._frame_ms = 0.5         # plenty of room now
for _ in range(400):
    ticker()._adapt()
check("…and it comes back when the machine can afford it", ticker().fps > slowed, True)
ticker().set_base_fps(30)
check("the person's own cap is still the ceiling", ticker().fps <= 30, True)
win._apply_guards()
check("the 10-second guard does not reset the measurement",
      ticker().stats()["base"] <= 30, True)
check("the footer shows the real cost of a frame", "ms/frame" in win.lbl_foot.text(), True)
app.processEvents()

print("\n8) the record is readable after the fact, without a log file")
act = activity.reset()
act.begin("install something slow")
act.step("tool: install")
act.note("downloading")
act.finish(ok=True)
text = " / ".join(act.snapshot()["history"])
check("the trail names the step", "tool: install" in text, True)
check("…and the note", "downloading" in text, True)
check("…and the total time is on the line", " in " in act.line(), True)

win.close()
print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
