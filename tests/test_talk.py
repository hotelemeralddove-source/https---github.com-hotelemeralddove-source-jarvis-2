"""Conversation mode, barge-in and memory — the three "it feels alive" rules.

None of these needs a microphone to test, because the decisions were written as
pure functions on purpose. The failures being locked out:

  * "thanks" being fed to the model as a new command;
  * "no" ending the conversation when the user just answered a question;
  * a single loud frame (chair, door, click) cutting ARC off mid-sentence;
  * ARC being unable to hear anything because the room is loud;
  * ARC learning that your name is "not" or that you use vim because you asked
    "do I use vim?".

Run:  python tests/test_talk.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-talk-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk import profile  # noqa: E402
from arcdesk.wake import talk  # noqa: E402


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<48} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def main() -> int:
    ok = True

    print("1) the chat ends when the user says it ends")
    for phrase in ("thanks", "Thanks da!", "that's all", "nothing else", "seri podhum",
                   "ok bye", "chalo", "theek hai", "nandri"):
        ok &= check(f"ends: {phrase}", talk.ends_conversation(phrase), True)
    for phrase in ("no", "no louder", "open chrome", "what time is it",
                   "thanks, open chrome", "ok"):
        ok &= check(f"continues: {phrase}", talk.ends_conversation(phrase), False)

    print("2) a cough is not a command")
    ok &= check("empty", talk.wants_followup(""), False)
    ok &= check("single letter", talk.wants_followup("a"), False)
    ok &= check("real words", talk.wants_followup("volume 20"), True)

    print("3) barge-in needs sustained speech, not one spike")
    ok &= check("one loud frame is ignored", talk.is_barge([100, 900, 100, 100]), False)
    ok &= check("four loud frames interrupt", talk.is_barge([900, 900, 900, 900]), True)
    ok &= check("quiet room never interrupts", talk.is_barge([80] * 12), False)
    ok &= check("speech after a pause still counts",
                talk.is_barge([80, 80, 900, 950, 1000, 1100]), True)
    ok &= check("threshold adapts up in a noisy room",
                talk.barge_threshold(300) > talk.barge_threshold(50), True)
    ok &= check("never below the speech floor", talk.barge_threshold(0) >= 500, True)

    print("4) memory learns facts, not grammar")
    ok &= check("name", profile.learn("my name is Arun").startswith("Remembered"), True)
    ok &= check("stored", profile.get("name"), "Arun")
    ok &= check("editor normalised", profile.learn("i use vscode"), "Remembered: your editor is VS Code.")
    ok &= check("asked, not stated", profile.learn("do I use vim?"), "")
    ok &= check("not a name", profile.learn("i am going home"), "")
    ok &= check("language", profile.learn("reply in tanglish"), "Remembered: your language is tanglish.")

    print("5) the profile reaches the prompt, briefly")
    summary = profile.summary()
    ok &= check("mentions the name", "Arun" in summary, True)
    ok &= check("stays small", len(summary) <= profile.LIMIT, True)
    ok &= check("one line", "\n" not in summary, True)

    print("6) the profile cannot smuggle anything executable")
    profile.set("name", "$(rm -rf ~)")
    ok &= check("stored as text", profile.get("name").startswith("$(rm"), True)
    ok &= check("and it is only text", profile.summary().count(";") >= 1, True)
    ok &= check("unknown key refused", profile.set("sudo", "yes").startswith("ERROR"), True)

    print("7) clearing works and is honest")
    ok &= check("clear", profile.reset().startswith("Profile cleared"), True)
    ok &= check("empty afterwards", profile.summary(), "")
    ok &= check("forget unknown is honest", profile.forget("city").startswith("I had nothing"), True)

    print("\n8) it listens patiently instead of running a stopwatch")
    # "porumaya kekanum... ena solluthu nu kooda puriyala" — the old loop had one flat
    # 7 s deadline and a 1.1 s tail, so a thinking pause ended the turn and a sentence
    # with a breath in it was cut in half.
    L = talk.listen_state
    ok &= check("still waiting for the first word at 6.9 s",
                L(spoken=False, quiet_for=0, elapsed=6.9, wait_for_speech=12), "wait")
    ok &= check("gives up only after the wait is over",
                L(spoken=False, quiet_for=0, elapsed=12.1, wait_for_speech=12), "stop")
    ok &= check("a breath mid-sentence does not end the turn",
                L(spoken=True, quiet_for=0.9, elapsed=20, wait_for_speech=12), "wait")
    ok &= check("…nor does a longer pause", 
                L(spoken=True, quiet_for=1.79, elapsed=20, wait_for_speech=12), "wait")
    ok &= check("two seconds of real silence does",
                L(spoken=True, quiet_for=1.9, elapsed=20, wait_for_speech=12), "stop")
    ok &= check("still talking at the deadline -> it keeps listening",
                L(spoken=True, quiet_for=0, elapsed=29, wait_for_speech=12), "wait")
    ok &= check("…but never forever", 
                L(spoken=True, quiet_for=0, elapsed=31, wait_for_speech=12), "stop")

    print("\n9) it does not answer itself")
    # The other half of "repeated ah pesitae iruku": the ears picking up our own speaker.
    ok &= check("its own sentence, heard a moment later, is ignored",
                talk.said_myself("the time is ten past nine", "The time is ten past nine."), True)
    ok &= check("…even in part", 
                talk.said_myself("ten past nine", "The time is ten past nine, machi."), True)
    ok &= check("a real short command is always obeyed",
                talk.said_myself("stop", "The time is ten past nine."), False)
    ok &= check("a different question is not mistaken for echo",
                talk.said_myself("what is the weather", "The time is ten past nine."), False)
    ok &= check("nothing said before -> nothing to ignore",
                talk.said_myself("open notepad", ""), False)

    print("\n10) one question, one answer")
    ok &= check("the same sentence twice in a row is dropped",
                talk.is_repeat("open notepad", "open notepad", 2.0), True)
    ok &= check("…including punctuation and case",
                talk.is_repeat("Open Notepad!", "open notepad", 1.0), True)
    ok &= check("saying it again later is a real command",
                talk.is_repeat("open notepad", "open notepad", 9.0), False)
    ok &= check("a different sentence is a different command",
                talk.is_repeat("open calculator", "open notepad", 1.0), False)
    ok &= check("short repeats still work (volume)",
                talk.is_repeat("louder", "louder", 2.0), True)

    print("\n11) the app actually hands these numbers to the daemon")
    root = Path(__file__).resolve().parents[1]
    runner = (root / "arcdesk" / "wake" / "daemon_runner.py").read_text(encoding="utf-8")
    window_src = (root / "arcdesk" / "widgets" / "window.py").read_text(encoding="utf-8")
    daemon = (root / "arc_daemon.py").read_text(encoding="utf-8")
    conf = (root / "arcdesk" / "config.py").read_text(encoding="utf-8")
    ok &= check("the daemon understands the three numbers",
                all(f"--{k}" in daemon for k in ("command-seconds", "silence-seconds",
                                                 "max-command-seconds")), True)
    ok &= check("the runner passes them on (it used to drop the setting entirely)",
                all(f"--{k}" in runner for k in ("command-seconds", "silence-seconds")), True)
    ok &= check("the window reads them from the settings",
                all(f"{k}=" in window_src for k in ("command_seconds", "silence_seconds")), True)
    ok &= check("the defaults are patient, not a stopwatch",
                ('"command_seconds": 12' in conf and '"silence_seconds": 1.8' in conf), True)
    ok &= check("the daemon asks the pure rules, not its own arithmetic",
                "talk.listen_state(" in daemon and "talk.said_myself(" in daemon
                and "talk.is_repeat(" in daemon, True)
    ok &= check("the app tells the daemon what it is about to say",
                '"said"' in window_src and 'msg.get("event") == "said"' in daemon, True)

    print("\n12) a follow-up said while it is answering is kept, not dropped")
    import time as _time
    from arcdesk.ai.agent import Agent

    class _Cfg(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    agent = Agent(_Cfg({"ai": {"enabled": False}}))
    ran: list[str] = []
    agent._run = lambda text: (ran.append(text), _time.sleep(0.2))   # noqa: SLF001
    agent.ask("what is my battery")
    _time.sleep(0.05)
    agent.ask("and the CPU")
    _time.sleep(0.7)
    ok &= check("the follow-up was run, not thrown away", ran, ["what is my battery",
                                                                "and the CPU"])
    ok &= check("and nothing is left pending afterwards", agent._pending, "")   # noqa: SLF001
    agent.ask("one more")
    _time.sleep(0.4)
    ok &= check("a later request still runs normally", ran[-1], "one more")

    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
