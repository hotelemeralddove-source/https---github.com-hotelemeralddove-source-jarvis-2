"""The rules of a conversation — kept as pure functions so they can be tested.

Three decisions the voice daemon has to make between turns, and all three are
easier to get wrong than they look:

  * **when the conversation is over** — you said "thanks", not another command;
  * **when you are interrupting** — sustained speech, not one loud frame from a
    chair creak or the tail of JARVIS's own sentence in the speakers;
  * **when a follow-up is real work** — so a cough does not become an empty turn.

Everything here is a pure function of (text, levels). No microphone, no Qt, no
sockets, so `tests/test_talk.py` can hammer the edges without any hardware.
"""
from __future__ import annotations

import re

# Deliberately complete phrases, not keywords: "no" alone is a valid answer to a
# question ("do you want it louder?" → "no"), so only the full shrug counts.
ENDINGS = {
    "thanks", "thank you", "thanks da", "thank you da", "thats all", "that is all",
    "that's all", "nothing else", "no thanks", "ok thanks", "okay thanks",
    "good bye", "goodbye", "bye", "ok bye", "cool thanks", "nice thanks",
    "nandri", "romba nandri", "seri", "seri podhum", "podhum", "chalo",
    "theek hai", "bas", "bas karo",
}

# "no" and "stop" are handled elsewhere: stop silences speech, no is an answer.


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s']", " ", (text or "").lower()).strip()


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", _norm(text))


def ends_conversation(text: str) -> bool:
    """True when the user is closing the chat rather than asking something."""
    said = _squash(text)
    if not said:
        return False
    if said in ENDINGS:
        return True
    # "thanks, that's all" / "ok thanks da, nothing else"
    words = said.split()
    if len(words) <= 5 and any(said == e for e in ENDINGS):
        return True
    if len(words) <= 5 and said.rstrip("s") in {e.rstrip("s") for e in ENDINGS}:
        return True
    return False


def wants_followup(text: str, min_chars: int = 2) -> bool:
    """Is this worth treating as a command? A cough transcribes as nothing."""
    said = _norm(text)
    return len(said.replace(" ", "")) >= min_chars


def is_barge(levels: list[int], threshold: int = 700, frames: int = 4) -> bool:
    """Sustained loud speech = you started talking over JARVIS.

    `frames` consecutive frames above `threshold`. A single spike (a click, a
    door) fails; the tail of JARVIS's own voice through speakers does not usually
    hold four frames at speaking volume, and when it does, we err on the side of
    listening — being interrupted is better than being ignored.

    Levels are int16 RMS values, so ~700 is quiet speech and ~3000 is close-mic talk.
    """
    run = 0
    for level in levels:
        if level >= threshold:
            run += 1
            if run >= frames:
                return True
        else:
            run = 0
    return False


def barge_threshold(noise_floor: int) -> int:
    """Adapt to the room: loud fans need a higher bar than a silent bedroom."""
    floor = max(0, int(noise_floor))
    return max(500, int(floor * 3 + 400))


# --------------------------------------------------------------------- patience
# The report: "repeated ah pesitae iruku, porumaya kekanum, analyse pananum... but
# confuse aagi pesitu iruku". Three separate faults, and each one is a decision this
# file can make without a microphone:

#  1. it stopped listening too early   -> listen_state()
#  2. it heard its own voice and answered it -> said_myself()
#  3. it acted on the same sentence twice     -> is_repeat()

def listen_state(*, spoken: bool, quiet_for: float, elapsed: float,
                 wait_for_speech: float, silence_seconds: float = 1.8,
                 max_seconds: float = 30.0) -> str:
    """Should the ears keep listening? "wait" or "stop".

    * no speech yet  -> wait until `wait_for_speech` (a person needs a moment to think
      after "hey jarvis"; cutting at 7 s made it look like it was not listening);
    * speech started -> stop only after `silence_seconds` of quiet, which is long enough
      for a breath in the middle of a Tamil sentence;
    * still talking at the deadline -> keep going until `max_seconds`, because cutting
      someone off mid-sentence is exactly what "porumaya kekanum" was about.
    """
    if elapsed >= max_seconds:
        return "stop"
    if not spoken:
        return "stop" if elapsed >= wait_for_speech else "wait"
    if quiet_for >= silence_seconds:
        return "stop"
    return "wait"


def _similar(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, _squash(a), _squash(b)).ratio()


def said_myself(heard: str, last_spoken: str, threshold: float = 0.78) -> bool:
    """True when the microphone picked up JARVIS's own answer.

    Half duplex only works if the mute arrives in time; a speaker tail, a Bluetooth
    headset's latency or a phone on the desk can put our own sentence into the ears a
    moment after the mute lifts. Then it "answers itself", out loud, forever — the
    "repeated ah pesitae iruku" complaint. A short utterance is never treated as echo,
    because "stop" or "illa" must always be obeyed.
    """
    said = _squash(heard)
    mine = _squash(last_spoken)
    if not said or not mine:
        return False
    if len(said) < 8 or len(mine) < 8:
        return False
    if said in mine:
        return True
    return _similar(said, mine) >= threshold


def is_repeat(heard: str, previous: str, seconds_apart: float,
              window: float = 8.0, threshold: float = 0.92) -> bool:
    """True when this is the same sentence the recogniser already handed us.

    Speech recognisers re-fire on a long utterance, and the daemon used to run the same
    command twice — two answers to one question is the confusion the person heard.
    Only consecutive turns, only inside a few seconds, and only when nearly identical:
    genuinely saying "louder" twice must still work.
    """
    if seconds_apart > window:
        return False
    if not _squash(heard) or not _squash(previous):
        return False
    return _similar(heard, previous) >= threshold
