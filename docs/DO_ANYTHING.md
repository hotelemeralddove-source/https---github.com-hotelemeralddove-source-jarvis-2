# "Do what I say" — the honest ledger

You asked for a JARVIS: say it, it happens. This page is the truth about that, task by
task, written before the marketing version. Status is measured today, not promised.

**54 built-in tools · 65 more via MCP · 4 of them gated behind a click · every action
journalled.** Vocabulary ARC understands offline: `COMMANDS.md`. Numbers: `CAPABILITIES.md`.

---

## 1. What it does, right now, when you say it

| You say | ARC does | Where it works |
|---|---|---|
| "open notepad", "open spotify" | launches the app | ✅ Windows / macOS / Linux |
| "open youtube", "go to github" | opens the site | ✅ |
| "open notepad and type hello" | two actions, one sentence | ✅ Windows |
| "type good morning" | types into the focused window | ✅ Windows |
| "press ctrl s", "press enter" | key chords | ✅ Windows |
| "list windows", "switch to chrome", "minimize everything" | window control | ✅ Windows · ⚠️ Linux needs `xdotool` |
| "what is eating my ram", "system status" | live CPU / RAM / disk / top processes | ✅ |
| "set volume 30", "mute", "next song" | media & audio | ✅ Windows/macOS/Linux |
| "brightness 60", "screenshot" | display | ✅ |
| "create folder projects" | makes it in your home | ✅ |
| "write hello to the file notes.txt" | writes, keeping a `.bak` of the old one | ✅ |
| "read the file notes.txt" | 200 lines / 64 KB cap | ✅ |
| "delete the file notes.txt" | to the trash | ✅ **asks first** |
| "run command echo hi" | shell command, output capped | ✅ **asks first**, 15 patterns refused |
| "timer 10 minutes", "note buy milk", "read notes" | timers, memory | ✅ |
| "find report.docx" | read-only search of Desktop/Documents/Downloads/Pictures | ✅ |
| "what did you do" | journal of every action it took | ✅ |
| "draw an elephant", "make it purple" | draws and edits | ✅ offline, ~3 ms |
| "hey jarvis" / "bye jarvis" | opens / closes the world | ✅ (needs `vosk` for voice) |
| "shut down", "restart", "lock" | power | ✅ **asks first** |
| "summarise this page", "read this URL" | page reading | ✅ with the **Fetch** MCP server |
| "check my git repo", "search this folder", "think step by step" | 65 MCP tools | ✅ when enabled |
| "write a reply to this email", "plan my week", "explain this error" | reasoning | ✅ with a brain (free Groq/Gemini key or local Ollama) |
| "what does this error say", "read my screen" | OCR of the screen | ✅ needs Tesseract (`INSTALL.md` §7) |
| "click Send", "click the Export button" | accessibility tree first, then OCR + pixel click | ✅ Windows/macOS; Linux needs `xdotool` (+`pyatspi` for the tree) |
| "email raj@x.com about the invoice" | SMTP send, password from an env var | ✅ once configured, **asks first** |
| "what's on my calendar", "add a meeting at 4pm tomorrow" | real `.ics` files | ✅ no account needed |
| "WhatsApp Raj that I'm late" | opens the message, pre-filled | ⚠️ you press send |

---

## 2. What it cannot do — and why, in plain words

| Task | Why not | What would fix it |
|---|---|---|
| "click the **blue** button" when it has no text (an icon) | OCR reads words; there is no icon/template matching yet | template matching or a vision model |
| "edit this .docx / .xlsx" | no Office format library | `python-docx` / `openpyxl`, ~10 MB together |
| Reading a mailbox / sending automatically | SMTP sends, but there is no IMAP inbox reader yet | `imaplib` + an app password, ~40 lines |
| Google Calendar sync (not just `.ics`) | OAuth needs a Google project and a stored token | `.ics` subscription covers read-only today |
| "buy this for me" | **refused by design** | nothing — ARC will not spend money or enter payment details |
| "control my lights / AC" | no IoT bridge | MQTT / Home Assistant bridge |
| "remember what we discussed last month" | session memory + one notes file only | a local vector store over the notes file |
| "do this 12-step task in one go" | the agent stops after **4 tool rounds** on purpose | raise `MAX_TOOL_ROUNDS`, at the cost of runaway loops |
| Anything needing admin rights | **refused by design** | nothing — no `runas`, no `sudo`, ever |

The pattern: **ARC can drive your machine, and cannot act as you anywhere that
requires your identity, your money or your privileges.** That line is what makes it safe
to leave running.

---

## 3. How "anything you say" is kept from becoming "anything a misheard word says"

Four walls, all in code, all tested (`tests/test_actions.py`):

1. **Data loss needs your click.** `file_delete`, `run_command`, `close_app`, `power` are
   `confirm=True`. The agent loop freezes, shows the exact command, and waits 45 s. No
   answer = denied. The default button is **No**.
2. **Nothing is destroyed quietly.** Writing over a file keeps `<name>.<timestamp>.bak`.
   Deleting uses the OS trash when there is one.
3. **Writes stay in your home folder.** `/etc`, `C:\Windows`, `../../` — refused with a
   reason, not a stack trace.
4. **Irreversible commands are refused by pattern** before a process is spawned: disk
   format, partitioning, boot config, registry deletion, recursive root deletes, fork
   bombs, `curl … | sh`, privilege escalation. If you genuinely need one, you run it.

And one more that is not a wall but a receipt: **`~/ArcDesk/logs/actions.log`**. Every
action, its arguments, and its outcome. Ask *"what did you do"* and you get it back.

---

## 4. What is still missing before it feels like JARVIS

Ordered by how much the assistant improves per hour of work:

1. **Eyes** — screen capture + OCR, so "what does this error say" works.
2. **Inside apps** — UIAutomation on Windows: click, read lists, fill forms.
3. **Voice that sounds human** — Kokoro or Piper via `sherpa-onnx` (`GITHUB.md` §2).
4. **Real memory** — an index over the notes file and the action journal, so "like last time"
   means something.
5. **Plans, not single calls** — let it propose a 6-step plan, show it, then run it.
6. **Office files** — `python-docx` / `openpyxl` for the documents people actually get.

None of these need a paid service, and none of them require copying someone else's app —
they are backends, invoked over localhost or the CLI, credited in `CREDITS.md`.
