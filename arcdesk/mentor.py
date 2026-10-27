"""Lateral thinking and mentoring — better questions, not confident answers.

There is a real difference between a mentor and an oracle. A mentor asks the
question you were avoiding, names the assumption you did not notice, and gives you a
structure to think in. An oracle guesses and sounds certain.

This module is deliberately the first kind. Every tool returns a **worked scaffold**
with prompts, counter-examples and a next action. When you ask it to think for you,
it says so: `refuse_to_guess()` explains why, and gives you the frame to fill.
"""
from __future__ import annotations


def scamper(problem: str = "") -> str:
    p = (problem or "[your product / process]").strip()
    return f"""SCAMPER · {p}

  Substitute   What part of {p} could be swapped for something cheaper or simpler?
  Combine      What could {p} be paired with that would double its usefulness?
  Adapt        What does another industry already do that would work here?
  Modify       What would change if it were 10× smaller, faster, or free?
  Put to use   What else is {p} already good at that nobody is paying for?
  Eliminate    Which step exists only because it always has?
  Reverse      What if the customer did the work and you did the waiting?

Pick the one line you can test in a week. Cross out the other six. A SCAMPER where
nothing is crossed out is a list, not a decision."""


def six_hats(topic: str = "") -> str:
    t = (topic or "[the decision]").strip()
    return f"""Six thinking hats · {t}

  WHITE  facts only: what do we know, what is missing, what would we measure?
  RED    gut: what does your stomach say, before any justification?
  BLACK  risk: how does this fail, who gets hurt, what does it cost when it does?
  YELLOW best case: what is the strongest version of this working?
  GREEN  alternatives: what else could solve the same job completely differently?
  BLUE   process: which hat are we actually wearing right now?

Do them in that order, in writing, and do not let one hat argue with another until
all six are on paper. Most bad decisions are one hat doing all the talking."""


def invert(goal: str = "") -> str:
    g = (goal or "[your goal]").strip()
    return f"""Inversion · {g}

Instead of "how do I achieve {g}?", answer: **how would I guarantee failure?**

  1. What would make {g} impossible in 30 days? (list five, honestly)
  2. Which of those am I already doing, a little?
  3. What is the cheapest way to stop the top one this week?

Why this works: the list of ways to fail is usually shorter, more concrete, and more
actionable than the list of ways to succeed. Avoiding stupidity is easier than
seeking brilliance — and it compounds faster."""


def five_whys(problem: str = "") -> str:
    p = (problem or "[the problem]").strip()
    return f"""Five whys · {p}

  1. Why does {p} happen?        → because ___
  2. Why does that happen?       → because ___
  3. Why does that happen?       → because ___
  4. Why does that happen?       → because ___
  5. Why does that happen?       → because ___

Stop when the answer is something you can change on Monday. If you reach step 5 and
the answer is still "because people are like that", the chain went sideways: go back
to the step where the answer became a person instead of a process.

Warning, from experience: five whys finds *a* root cause, not *the* root cause. Use
it to find one thing worth fixing, not to close an investigation."""


def pre_mortem(plan: str = "") -> str:
    p = (plan or "[your plan]").strip()
    return f"""Pre-mortem · {p}

It is 6 months from now and {p} failed. Not dramatically — it just quietly did not
work. Write the story of why, in the past tense:

  1. What did we run out of first: money, attention, or trust?
  2. Who stopped caring, and on which day?
  3. What did we keep telling ourselves that was not true?
  4. What did a competitor, a platform or the weather do that we ignored?
  5. Which single decision, made in week one, looks obvious in hindsight?

Now the useful part: for the top two, name the cheapest early warning sign you could
watch *this week*. A pre-mortem that does not change one decision is entertainment."""


def first_principles(problem: str = "") -> str:
    p = (problem or "[the problem]").strip()
    return f"""First principles · {p}

  1. What do I actually want? (the outcome, not the product)
  2. What do I know is physically true here? (costs, time, laws, materials)
  3. What am I assuming because everyone says it? (write the list)
  4. Which assumption, if false, changes everything?
  5. If I built this from zero with today's tools, what would it look like?

Then compare that sketch with what you are about to do. The gap between them is
where the money is — usually because an old constraint stopped being true and nobody
re-checked it."""


def second_order(decision: str = "") -> str:
    d = (decision or "[your decision]").strip()
    return f"""Second-order thinking · {d}

  First order:  if I do {d}, what happens next?
  Second order: and then what happens, because that happened?
  Third order:  and then what, six months later?

Three classic patterns worth checking:
  · the fix that removes today's pain and creates tomorrow's dependency
  · the win that trains the other side to behave worse (discounts, free work)
  · the shortcut that works once and quietly sets the standard

Write one sentence per order. If the third-order sentence is something you would not
accept on purpose, the decision is not as small as it looks."""


def questions(topic: str = "", n: int = 10) -> str:
    t = (topic or "[your situation]").strip()
    bank = [
        f"What would have to be true for {t} to be easy?",
        f"What is the smallest version of {t} that would still be worth doing?",
        "Who has already solved this, and what did it cost them?",
        f"What would you do about {t} if you could not tell anyone?",
        f"What is the decision you are avoiding by working on {t}?",
        "What would you advise a friend in exactly this spot?",
        "What does done look like, in a way someone could photograph?",
        f"Which part of {t} is only hard because it is unfamiliar?",
        f"What are you protecting by not starting {t}?",
        f"If {t} doubled in size next month, what would break first?",
        "Where is the constraint: money, time, skill, or permission?",
        f"What would you stop doing to make room for {t}?",
    ]
    n = max(3, min(int(n), len(bank)))
    return f"{n} questions about {t}:\n" + "\n".join(
        f"  {i}. {q}" for i, q in enumerate(bank[:n], 1))


def principles_list() -> str:
    return """Thinking rules I actually use (and will hold you to)

  1. Separate the decision from the outcome. A good call can have a bad result.
  2. Write the reason down *before* you know if it worked, or you will rewrite it after.
  3. Prefer reversible decisions made fast; slow down for one-way doors.
  4. If two options are close, the criteria are vague — fix the criteria.
  5. Ask what would change your mind. If nothing would, you are not deciding, you
     are defending.
  6. Watch base rates before you believe your own story about being different.
  7. The cheapest test beats the best plan."""


def mentor(mode: str = "questions", subject: str = "") -> str:
    table = {"scamper": scamper, "six_hats": six_hats, "sixhats": six_hats,
             "invert": invert, "five_whys": five_whys, "whys": five_whys,
             "pre_mortem": pre_mortem, "premortem": pre_mortem,
             "first_principles": first_principles, "principles": first_principles,
             "second_order": second_order, "questions": questions}
    fn = table.get((mode or "questions").lower().strip().replace("-", "_"))
    if fn is None:
        return ("Frames I have: " + ", ".join(sorted(set(table))) +
                ". Say 'mentor six hats <topic>'.")
    return fn(subject)


def refuse_to_guess() -> str:
    """When the user asks JARVIS to simply decide for them."""
    return ("I will not pretend to think for you and hand you a confident answer — "
            "that is the one thing a mentor must never do, because you will act on it.\n\n"
            "What I can do:\n"
            "  · lay out the decision with its assumptions written down\n"
            "  · list what would have to be true for each option\n"
            "  · name the cheapest test that would settle it this week\n"
            "  · hold the frame while you choose\n\n"
            "Say 'mentor invert <goal>' or 'mentor pre-mortem <plan>' and we start.")
