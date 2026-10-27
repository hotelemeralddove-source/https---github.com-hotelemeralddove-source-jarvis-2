# What ARC will not do, and what it does instead

This page exists because the list of requests grew, and "no" without a reason is just
a broken feature. Every refusal below is **in the code**, not in a policy document: the
handler returns the reason and the lawful alternative. If a refusal ever disappears from
the code, `tests/test_mind.py` and `tests/test_actions.py` go red.

---

## 1. Hacking, cracking, and "access anything anywhere"

| You ask | ARC says | Instead |
|---|---|---|
| "hack my neighbour's wifi" | no — and it explains why | `secure{posture}`: is *your* network using WPA3, WPS off, router firmware current |
| "break this password hash" / "crack my ex's password" | no | `secure{password}`: entropy, search space, and how long *your own* password would last, plus what to change |
| "get me into this Instagram account" | no | `secure{recovery}`: the legitimate recovery path, and what to do if it is *your* account |
| "hollow operation" / "silently access their machine" / "access anything anywhere" | no | nothing — a desktop assistant that can quietly open a door on someone else's machine is a backdoor, and antivirus would be right to flag the whole program |
| "make ARC invisible to antivirus" | no | — |
| "make ARC impossible to kill / hide the process" | no | `Ctrl+Alt+Q` always quits. A process the owner cannot stop is malware, whatever the intent |

**Why this is not negotiable.** Unauthorised access is a criminal offence in India
(IT Act s.66 and s.43) and most other jurisdictions; the tools needed for it cannot be
built "just for testing" without shipping the capability to everyone who installs the
app. And the second reason is engineering: every trick that hides ARC from a security
product also hides it from *you*.

**What is built instead** — the defensive half, which is the half that actually helps:

```bat
python tools\explain.py "how strong is my password Tr0ub4dor&3"
```

- `secure{password}` — entropy in bits, character-class search space, crack time at
  1e10 guesses/s, and the specific weakness ("it is a dictionary word + year").
  The password is never stored, never logged, never sent anywhere.
- `secure{phishing}` — signal-by-signal scoring (lookalike domain, urgency, credential
  request, mismatched link text) with a HIGH/MEDIUM/LOW verdict and the exact lines that
  triggered it.
- `secure{posture}` — this machine: firewall, OS build, disk encryption, open ports,
  patched browser, guest account.
- `secure{recovery}` — a printed recovery plan for your own accounts.

---

## 2. Claims ARC cannot back with a source

| You ask | ARC says | Instead |
|---|---|---|
| "who won the 2024 election" | *"I do not know that one, and I will not improvise it"* | a real search link, and an offer to read pasted text |
| "gold price today" | the same | a live quote tool if the network is up, otherwise the link |
| "what will the market do tomorrow" | it will not say | `foresight{forecast}`: a line through past numbers, with an error band, labelled as exactly that |
| "tell me about my customer's revenue" | it has no such data | `mine{report}` on the CSV you actually have, with `n` printed |
| "how much paracetamol should I take" | never a personal dose | the published label range + "ask a pharmacist" (`health`) |
| "add captions to this video" with no transcript | no invention | `video_studio` burns an `.srt` you provide; the words need a local ASR model (`faster-whisper`), not a guess |
| "put background music on this" with no file | no synthesised track | it names the path it wanted — a generated bed would be an unlicensed invention, not music |
| "guarantee this post will go viral" | no | hook styles, word counts, a real posting calendar — and a line saying engagement depends on the audience |

**"Knows everything" means:** a shelf of 75 sourced and dated facts, arithmetic for
anything countable, your own indexed files quoted by name, a live Wikipedia lookup that
cites its date — and the word *"I do not know"* for everything else. See
`CAPABILITIES.md` §"The library" and `tests/test_world.py`, which fails the build if an
entry loses its source or its year.

---

## 3. Money and lock-in

| Refused | Why | What exists |
|---|---|---|
| paid APIs as the default | the app must cost ₹0 forever | free local engines + free-tier keys, enforced by a guard that refuses a paid key *before* the request |
| subscriptions, trials, "pro" tiers | — | `FREE.md`, and `tests/test_free_guard.py` |
| copying an open-source app into the repo | licence laundering | engines run as separate processes over localhost/CLI; `CREDITS.md` + `OPEN_SOURCE.md` |

---

## 4. Damaging your own machine

| Refused | Why | What exists |
|---|---|---|
| replacing Explorer / killing the shell | the desktop must stay a normal Windows 11 Pro | a fullscreen window that *covers* the taskbar, j+auto-restore, `HKCU` only, no admin (`MAGIC.md`) |
| editing your files in place | a bad edit is unrecoverable | every edit writes a **new sibling file** with a timestamp |
| deleting files without asking | — | `file_delete` is confirm-gated and journaled |
| uninstalling without a trace | — | `uninstall.bat`, and the journal shows exactly what was changed |

---

## The one-line rule

> If answering would require inventing a fact, opening someone else's door, or leaving
> the machine worse than it was found — ARC says no, in the code, and offers the lawful
> thing that actually helps.
