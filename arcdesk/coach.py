"""The part that is not a tool: a mentor, an analyst, and something that listens.

Four jobs, kept separate on purpose, because mixing them is how assistants become
useless ("here are 5 productivity tips!" when someone says they are exhausted):

* **listen** — name what was said, validate it, ask one question, offer one small step.
  No toxic positivity, no diagnosis, no pretending to be a therapist.
* **mentor** — Socratic questions, a 7-day plan, one action for today, a way to tell if
  it worked. Advice is labelled as a suggestion, never as certainty.
* **analyst** — separate *fact* (measured), *inference* (reasoned) and *guess*
  (invented). If the numbers are missing, ask for them instead of inventing them.
* **decide** — reversible vs one-way-door test, weighted criteria, a recommendation with
  its confidence and the reason it could be wrong.

Everything is local. A journal entry never leaves the machine, and mood counts are
counted from the entries that exist — not estimated.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

MODES = ("listen", "mentor", "analyst", "decide", "plan", "checkin", "journal",
         "reflection")

CRISIS = re.compile(
    r"\b(kill myself|kill me|end my life|ending it all|suicide|suicidal|want to die|"
    r"better off dead|no reason to live|hurt myself|self.?harm|cut myself|"
    r"not want to live)\b", re.I)

DISTRESS = {
    "anxious": r"\b(anxious|anxiety|panic|worried|worrying|nervous|overthink\w*|"
               r"tension|fear|scared)\b",
    "low": r"\b(sad|low|depress\w*|crying|cry|hopeless|empty|down|blue|broken|heavy)\b",
    "tired": r"\b(tired|exhaust\w*|burn\w*out|drained|no energy|sleepy|no sleep|"
             r"can.?t sleep|didn.?t sleep)\b",
    "angry": r"\b(angry|furious|irritated|frustrat\w*|fed up|annoyed|rage)\b",
    "lonely": r"\b(lonely|alone|nobody|no one|isolated|left out)\b",
    "stuck": r"\b(stuck|confused|lost|no idea|don.?t know what to do|paralys\w*)\b",
    "overwhelmed": r"\b(overwhelm\w*|too much|can.?t handle|drowning|pressure)\b",
}

DECISION = re.compile(r"\b(should i|shall i|should we|which (one|is better)|"
                      r"decide|decision|confused between|or should|worth it)\b", re.I)
GOAL = re.compile(r"\b(i want to|i need to|my goal|help me plan|how do i start|"
                  r"where do i start|plan for)\b", re.I)

TANGLISH = ("machi", "da", "di", "romba", "seri", "illa", "pannu", "podhu", "thambi",
            "akka", "enna", "epdi", "sollu", "nu", "la", "ku")

HELP_LINES = (
    "If it ever gets to the point where you might act on it, please talk to a person "
    "right now:\n"
    "  · India: Tele-MANAS 14416 (24×7, free) · KIRAN 1800-599-0019\n"
    "  · Elsewhere: your local emergency number (112 in India, 988 in the US, 116 123 UK)\n"
    "  · Or a friend — literally one message: \"I'm not okay, can you call me?\""
)


# --------------------------------------------------------------- journal (local)
def _journal_path() -> Path:
    from . import config
    folder = config.data_dir() / "coach"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "journal.jsonl"


def mood_of(text: str) -> str:
    low = (text or "").lower()
    for mood, pattern in DISTRESS.items():
        if re.search(pattern, low):
            return mood
    if re.search(r"\b(good|great|happy|proud|calm|grateful|excited|relieved|better|"
                 r"worked well|slept well)\b", low):
        return "good"
    return "neutral"


def journal(text: str = "", mood: str = "") -> str:
    body = (text or "").strip()
    if not body:
        return "What should I write down? One line is enough."
    entry = {"at": time.time(), "mood": (mood or mood_of(body)).lower(), "text": body[:900]}
    try:
        with _journal_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception as exc:
        return f"I could not write that down ({type(exc).__name__}). Nothing was saved."
    reply = (f"Saved to your private journal — {time.strftime('%d %b %H:%M')}. "
             f"I read it as “{entry['mood']}”; it stays on this machine.")
    if entry["mood"] not in ("good", "neutral"):
        reply += ("\nNo advice unless you want it. If you do: say 'help me think about it'.")
    return reply


def reflection(days: int = 7) -> str:
    """Counts from the entries that actually exist. No estimates."""
    path = _journal_path()
    if not path.exists():
        return "No journal entries yet, so there is nothing to count — I will not invent one."
    cutoff = time.time() - max(1, int(days)) * 86400
    entries = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("at", 0) >= cutoff:
                entries.append(row)
    except Exception:
        return "I could not read the journal file."
    if not entries:
        return f"No entries in the last {days} days."
    counts: dict[str, int] = {}
    for row in entries:
        counts[row.get("mood", "neutral")] = counts.get(row.get("mood", "neutral"), 0) + 1
    order = sorted(counts.items(), key=lambda kv: -kv[1])
    lines = [f"{len(entries)} entries in the last {days} days:"]
    lines += [f"  {mood:12} {count}  ({count / len(entries) * 100:.0f}%)"
              for mood, count in order]
    heavy = sum(count for mood, count in order if mood not in ("good", "neutral"))
    if heavy:
        lines.append(f"{heavy} of {len(entries)} were heavy days. That is a pattern worth "
                     f"naming, not a verdict — what happened on those days?")
    else:
        lines.append("Mostly steady. Worth noting what you were doing on the good days.")
    return "\n".join(lines)


# ------------------------------------------------------------------- responses
def _tanglish_tail(text: str) -> str:
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return ("\n\nMachi, neenga solradhu puriyudhu — dheiriyama irunga."
            if words & set(TANGLISH) else "")


def _listen(text: str) -> str:
    low = text.lower()
    mood = mood_of(text)
    opening = {
        "anxious": "That sounds like a lot of pressure to carry, and anxiety is a normal "
                   "response to uncertainty — not a character flaw.",
        "low": "What you are describing sounds heavy. You do not have to explain it "
               "better than that for it to count.",
        "tired": "Tired is information, not laziness. Something in your week is taking "
                 "more than it gives back.",
        "angry": "Anger usually shows up when something you value got stepped on. "
                 "Worth naming what got stepped on.",
        "lonely": "Feeling unseen is its own kind of tired. It does not mean something "
                  "is wrong with you.",
        "stuck": "Being stuck usually means the options you have been given are not the "
                 "only ones. Let's widen the frame.",
        "overwhelmed": "When everything arrives at once, the fix is never 'try harder'. "
                       "It is 'make the list smaller'.",
        "good": "Good to hear it. Worth noticing what made it good, so it is repeatable.",
        "neutral": "I'm here. Tell me the part that is loudest right now.",
    }.get(mood, "I'm here.")
    body = [opening, "", "One question, not five: what would make tomorrow feel 10% "
                         "lighter — not perfect, just lighter?"]
    if mood in ("tired", "overwhelmed", "anxious"):
        body += ["", "If you cannot answer that, the honest next step is not advice: "
                     "it is water, food, or sleep. Any order."]
    if re.search(r"\b(alone|nobody|no one)\b", low):
        body += ["", "And if the loneliness is the loudest part: send one message to one "
                     "person today, even a boring one. Connection rarely arrives on its own."]
    body += ["", "I can also just sit with it — say 'talk to me', or 'help me think "
                 "about it' when you want structure instead of company."]
    return "\n".join(body) + _tanglish_tail(text)


def _mentor(text: str) -> str:
    topic = re.sub(r"^\s*(hey |ok |arc )?(mentor me|mentor|guide me|advice)( on| about)?\s*",
                   "", text, flags=re.I).strip(" .?") or "what you are working on"
    return "\n".join([
        f"Let's treat “{topic}” as a skill problem, not a willpower problem.",
        "",
        "1. **Frame** — what does 'done' look like in one sentence? If you cannot write "
        "it, the goal is still a feeling. (That is normal, and it is step one.)",
        "2. **Smallest real move** — the action must be finishable today and produce "
        "evidence: a call, a page, a price, a message. Not 'research'.",
        "3. **Constraint** — what are you not allowed to use? Time, money, permission. "
        "Constraints are what make advice specific.",
        "4. **Feedback** — who sees the first version in 72 hours? A plan with no "
        "viewer is a diary entry.",
        "5. **Kill criteria** — decide now what would make you stop or change course. "
        "People who skip this keep a bad idea alive for a year out of pride.",
        "",
        "Tell me two things and I will turn it into a seven-day plan with a name on "
        "each day: what 'done' looks like, and your biggest constraint.",
        "",
        "_(This is a framework, not a prophecy. The plan will only be as good as the "
        "facts you give me — I will not invent your numbers.)_",
    ]) + _tanglish_tail(text)


def _analyst(text: str, numbers: list[float] | None = None) -> str:
    numbers = numbers or [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]
    topic = re.sub(r"^\s*(analyse|analyze|as an analyst|what do you think about)\s*",
                   "", text, flags=re.I).strip(" .?") or "this"
    lines = [f"Analyst frame for “{topic}” — three buckets, kept separate:", ""]
    lines += [
        "**Fact** (something measured): " +
        (", ".join(f"{n:g}" for n in numbers[:8]) if numbers
         else "none given yet — so anything below is reasoning, not measurement."),
        "**Inference** (what the facts suggest): the direction matters more than the "
        "absolute number; one data point is a story, three is a trend.",
        "**Guess** (labelled as such): my default guess would be that the constraint is "
        "time or attention, not information. I would not bet on it.",
        "",
        "What would change my mind: a number that contradicts the direction, or a "
        "second independent source. Give me either and I will re-run this.",
        "",
        "Next three things I would actually do:",
        "  1. Write the decision as a question you can answer with data you can get "
        "this week.",
        "  2. List the two numbers that would settle it, and where they come from.",
        "  3. Set the threshold *before* you look — otherwise you will rationalise "
        "whatever you find.",
    ]
    if numbers and len(numbers) >= 3:
        try:
            from . import foresight
            lines += ["", "If these numbers are a series, I can extrapolate them with an "
                          "error band (say 'forecast " + " ".join(f"{n:g}" for n in numbers[:8])
                      + "') — labelled as arithmetic, never as certainty."]
            _ = foresight
        except Exception:
            pass
    return "\n".join(lines) + _tanglish_tail(text)


def _decide(text: str, options: list[str] | None = None) -> str:
    given = options or [o.strip() for o in re.split(r"\bor\b", text) if o.strip()][:4]
    lines = [
        "Let's make this a decision, not a mood. Three questions settle most of it:",
        "",
        "**1. Is it reversible?** Reversible decisions should be made fast and cheap — "
        "pick, try for two weeks, change your mind. One-way doors deserve the slow "
        "treatment. Most everyday choices are doors you can walk back through.",
        "**2. What are you actually optimising for?** Money, time, learning, peace, "
        "status, family — pick the top two. Two, not six; six is how decisions die.",
        "**3. What is the cost of *not* deciding?** Doing nothing is also a choice, and "
        "it is usually the most expensive one.",
        "",
    ]
    if len(given) >= 2:
        lines += [f"You mentioned {len(given)} paths: " + ", ".join(given[:4]) + ".",
                  "Score each 1–5 on your top two criteria, then multiply by the weight "
                  "you gave each criterion. If two options tie, the tie is the answer: "
                  "the difference was never the decision."]
    else:
        lines += ["Give me the options (say 'should I X or Y') and I will set up the "
                  "weighted comparison."]
    lines += ["",
              "**Recommendation:** if you cannot tell the options apart after that, choose "
              "the one that teaches you the most — you are buying information either way.",
              "",
              "Then run the pre-mortem: it is six months later and this failed. Write the "
              "three reasons in past tense. Any reason you cannot act on now is not a "
              "risk, it is a worry.",
              "",
              "_(My confidence in this frame: high. My confidence about your specific "
              "situation: unknown — I have only what you told me.)_"]
    return "\n".join(lines) + _tanglish_tail(text)


def _plan(text: str) -> str:
    goal = re.sub(r"^\s*(i want to|i need to|my goal is|help me plan|plan for me|"
                  r"how do i start)\s*", "", text, flags=re.I).strip(" .?") or "your goal"
    days = ["Write 'done' in one sentence + the one number that proves it.",
            "Smallest real action that produces evidence, not comfort.",
            "Show it to one person and ask for one objection.",
            "Fix the biggest objection; ignore the small ones this week.",
            "Do the boring repeat of what worked. Depth beats novelty.",
            "Cut one thing that is not working. Pruning is progress.",
            "Review: what did the week teach you? Keep, change, or stop."]
    lines = [f"Seven days for “{goal}”:", ""]
    lines += [f"  Day {i}: {step}" for i, step in enumerate(days, 1)]
    lines += ["",
              "Rules that make plans survive contact with real life: one action per day, "
              "each finishable in under 90 minutes, and a written 'stop' condition so "
              "quitting is a decision instead of a drift.",
              "",
              "I will not pretend to know your market or your numbers. If you give me the "
              "real ones, I can hold this plan up against them."]
    return "\n".join(lines) + _tanglish_tail(text)


def _checkin() -> str:
    return "\n".join([
        "A short check-in. Three lines, honest is enough:",
        "",
        "1. What did you finish this week that you would not have finished a year ago?",
        "2. What drained you most — and is it a person, a task, or a story you keep "
        "telling yourself?",
        "3. What is the one thing next week that, if it happened, would make the week "
        "feel worth it?",
        "",
        "Say 'journal <your answer>' if you want it kept. It stays on this machine.",
    ])


def respond(text: str = "", mode: str = "", options: list[str] | None = None,
            action: str = "") -> str:
    """One entry point. Detects the mode when the caller does not name one."""
    if action == "journal":
        return journal(text)
    if action == "reflection":
        days = int(re.search(r"\d+", text).group()) if re.search(r"\d+", text) else 7
        return reflection(days)
    if action == "checkin":
        return _checkin()

    body = (text or "").strip()
    if not body and not mode:
        return "I'm listening. What's going on?"

    if CRISIS.search(body):
        return ("I'm glad you said it out loud instead of carrying it alone. I am software "
                "— I cannot keep you safe, and you deserve someone who can.\n\n"
                + HELP_LINES + "\n\n"
                "While you reach someone: put the thing you would use to hurt yourself in "
                "another room, or hand it to someone. That sounds dramatic and it is the "
                "single most useful thing in the next ten minutes.\n"
                "When you are safe, I'm still here to help with the practical parts.")

    chosen = (mode or "").strip().lower()
    if not chosen:
        if DECISION.search(body):
            chosen = "decide"
        elif GOAL.search(body):
            chosen = "plan"
        elif mood_of(body) not in ("neutral", "good"):
            chosen = "listen"
        else:
            chosen = "mentor"

    if chosen == "listen":
        return _listen(body)
    if chosen == "analyst":
        return _analyst(body)
    if chosen == "decide":
        return _decide(body, options)
    if chosen == "plan":
        return _plan(body)
    if chosen == "checkin":
        return _checkin()
    return _mentor(body)


def limits() -> str:
    return ("I am a local assistant, not a therapist, doctor, or financial adviser. "
            "I do not diagnose, I do not claim certainty, and I keep what you tell me on "
            "this machine only. For anything that matters legally or medically, the "
            "answer is a person with a licence.")
