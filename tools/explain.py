#!/usr/bin/env python3
"""Trace one spoken command through ARC, stage by stage.

    python tools/explain.py "hey jarvis draw an elephant"
    python tools/explain.py "make it purple"
    python tools/explain.py --misheard
    python tools/explain.py "hey jervis open notepad" --fuzzy 0

This prints what actually happens between your mouth and the action, using the
real functions — the phrase matcher, the intent matcher, the tool registry and the
cost guard. Nothing is simulated except the microphone: stage 1 says so plainly.

It is also a debugging tool. When ARC "does not listen", this shows you which
stage disagreed: was it the wake word, the transcription, the intent or the tool?
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import config  # noqa: E402
from arcdesk.ai import cost, lite, tools  # noqa: E402
from arcdesk.wake import phrases  # noqa: E402

W = 74
SAFE = {"time", "system_report", "running_apps", "note", "read_notes", "find_file",
        "weather", "mcp_servers", "draw", "arc_mode", "charms", "magic", "timer"}
DANGEROUS = {"power", "close_app", "lock_screen", "clipboard", "set_volume", "mute",
             "media", "brightness", "screenshot", "open_app", "open_url", "web_search"}


def bar(c: str = "─") -> None:
    print(c * W)


def stage(n: int, title: str) -> None:
    print(f"\n[{n}] {title}")
    print("    " + "·" * (W - 4))


def say(label: str, value: str) -> None:
    print(f"    {label:<22} {value}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phrase", nargs="*", help='what you said, e.g. "hey jarvis draw a cat"')
    ap.add_argument("--fuzzy", type=int, default=1, choices=[0, 1])
    ap.add_argument("--misheard", action="store_true", help="show wake-word tolerance")
    ap.add_argument("--run", action="store_true", help="also execute non-destructive tools")
    ap.add_argument("--then", default="", metavar="PHRASE",
                    help='a follow-up command in the same session, e.g. --then "make it purple"')
    args = ap.parse_args()

    cfg = config.load()
    wake_cfg = cfg.get("wake", {}) or {}
    wake = str(wake_cfg.get("phrase") or "hey jarvis")
    exit_phrase = str(cfg.get("magic", {}).get("exit_phrase") or "bye jarvis")
    cmd_seconds = wake_cfg.get("command_seconds", 7)
    fuzzy = bool(args.fuzzy)

    if args.misheard:
        print("How the wake matcher handles a bad transcription "
              f"(phrase = {wake!r})\n")
        print(f"    {'engine heard':<34}{'result':<9}{'confidence'}")
        print("    " + "-" * 68)
        for heard in ("hey jarvis", "hey  jarvis", "hey jervis", "a jarvis", "jarvis",
                      "hey service", "hey darvis open notepad", "bye jarvis",
                      "goodbye jarvis", "hey what is the weather", "open notepad"):
            got = phrases.which(heard, wake, exit_phrase, fuzzy=fuzzy)
            print(f"    {heard!r:<34}{got or '(ignored)':<9}"
                  f"{phrases.confidence(heard, wake):.2f}")
        print("\n    'bye jarvis' is checked before the wake phrase, so the exit word can "
              "never\n    be mistaken for 'hey jarvis' — fuzzy matching only loosens the "
              "spelling,\n    never the meaning.")
        return 0

    text = " ".join(args.phrase).strip()
    if not text:
        ap.error("give me a phrase, e.g. \"hey jarvis draw an elephant\"")

    print(f"ARC DESK · command trace · \"{text}\"")
    bar("=")

    # ---------------------------------------------------------------- 1
    stage(1, "MICROPHONE (the only simulated stage)")
    say("source", "sounddevice → 16 kHz mono, 30 ms chunks")
    say("gate", "RMS below SILENCE_RMS is dropped, so silence costs nothing")
    say("note", "in this tracer the audio is skipped; the text is taken as heard")

    # ---------------------------------------------------------------- 2
    stage(2, "WAKE WORD — phrase matcher (arcdesk/wake/phrases.py)")
    kind = phrases.which(text, wake, exit_phrase, fuzzy=fuzzy)
    conf = phrases.confidence(text, wake)
    say("wake phrase", f"{wake!r}  ·  exit {exit_phrase!r}")
    say("match", f"{kind or '(not a wake phrase)'}   confidence {conf:.2f}")
    say("fuzzy", "on (jervis/jarvas/a jarvis accepted)" if fuzzy else "off (exact only)")
    if not kind:
        say("verdict", "IGNORED — nothing is sent to the app, nothing is executed")
        print()
        print("    Say the wake phrase first, then the command. With ARC Lite you can "
              "also\n    skip the wake word entirely by typing in the console (Ctrl+J).")
        return 0

    # ---------------------------------------------------------------- 3
    stage(3, "COMMAND WINDOW")
    say("opens for", f"{cmd_seconds} s, or until 1.1 s of silence after speech")
    say("exit phrase", f"{exit_phrase!r} inside this window returns to normal Windows")
    rest = phrases.strip_phrase(text, wake if kind == "wake" else exit_phrase)
    say("heard", repr(rest) if rest else "(nothing after the wake phrase)")

    if kind == "exit":
        print("\n    → sends {\"event\": \"exit\"}  →  wallpaper restored, ARC closes.")
        return 0

    # ---------------------------------------------------------------- 4
    stage(4, "SPEECH TO TEXT — Vosk, offline")
    say("engine", "vosk (streaming, partial + final results)")
    say("transcript", repr(rest or text))
    if not rest:
        say("verdict", "no command after the wake word — ask again in the same breath")
        return 0

    # ---------------------------------------------------------------- 5
    stage(5, "WHICH BRAIN")
    ai = cfg.get("ai", {}) or {}
    raw = str(ai.get("provider") or "auto")
    try:
        from arcdesk.ai.llm import detect_provider
        resolved = detect_provider(ai) if raw == "auto" else raw
    except Exception:
        resolved = "lite"
    limit = str((cfg.get("cost", {}) or {}).get("max_class", cost.MAX_DEFAULT))
    cls = cost.classify(resolved, str(ai.get("base_url") or ""))
    say("configured", f"{raw}" + ("" if raw == resolved else f" → {resolved}"))
    say("class", f"{cls} · limit {limit} · "
                 f"{'allowed' if cost.allowed(cls, limit) else 'BLOCKED'}")
    brain = "lite" if resolved == "lite" or not cost.allowed(cls, limit) else "llm"
    say("chosen", "ARC Lite (rule-based, offline)" if brain == "lite"
        else f"{resolved} (language model)")

    # ---------------------------------------------------------------- 6
    stage(6, "UNDERSTANDING — intent → tool call")
    if brain == "lite":
        spoken, calls = lite.respond(rest)
        say("matcher", "regex intents over the same tool registry the model uses")
        if calls:
            for c in calls:
                f = c["function"]
                say("tool", f"{f['name']}({f['arguments']})")
        else:
            say("tool", "(none)")
            say("reply", spoken[:160] or "(empty)")
            print()
            print("    ARC Lite answers directly when no tool is needed, and says so "
                  "honestly\n    when it does not understand instead of inventing an action.")
            return 0
    else:
        say("matcher", "the model chooses tools via function calling")
        say("schema", f"{len(tools.schemas())} tools offered (26 built-in + MCP)")
        say("rounds", "up to 4 tool rounds before it answers")
        calls = []
        say("tool", "(decided at runtime — needs a live model)")

    # ---------------------------------------------------------------- 7
    stage(7, "EXECUTION — tools.call()")
    results: list[str] = []
    for c in calls:
        name = c["function"]["name"]
        import json as _json
        argv = _json.loads(c["function"]["arguments"] or "{}")
        spec = tools.TOOLS.get(name)
        guard = "confirm=True (UI asks first)" if spec and spec.confirm else ""
        say(name, guard or "no confirmation needed")
        if args.run and name in SAFE:
            out = tools.call(name, argv)
            results.append(out)
            say("  →", " ".join(str(out).split())[:150])
        else:
            say("  →", "not executed here (add --run, or run it in the app)")

    # ---------------------------------------------------------------- 8
    stage(8, "REPLY")
    if results:
        final = " ".join(lite.summarise_tool_result(c["function"]["name"], r)
                         for c, r in zip(calls, results))
        say("text", " ".join(final.split())[:200])
    else:
        say("text", "(would summarise the tool output)")
    say("voice", "Windows SAPI (offline) or eSpeak — spoken only if AI voice is on")
    say("on screen", "console line + ARC's reply bubble")

    # ---------------------------------------------------------------- 9
    if args.then:
        stage(9, f"FOLLOW-UP IN THE SAME SESSION — \"{args.then}\"")
        t2 = phrases.strip_phrase(args.then, wake)
        say("wake word", "not needed again for a few seconds — the window stays open")
        say("transcript", repr(t2))
        spoken2, calls2 = lite.respond(t2)
        say("state", "the sketch from stage 7 is still in memory (tools.current_sketch)")
        if calls2:
            f = calls2[0]["function"]
            say("tool", f"{f['name']}({f['arguments']})")
            if args.run and f["name"] == "art_edit":
                out2 = tools.call(f["name"], __import__("json").loads(f["arguments"] or "{}"))
                say("  →", " ".join(str(out2).split())[:150])
        else:
            say("verdict", "no sketch in memory, so nothing to edit — ARC says so instead "
                           "of guessing")

    print()
    bar("=")
    print("Chain: mic → wake matcher → command window → Vosk → brain → intent → "
          "tool → reply")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())
