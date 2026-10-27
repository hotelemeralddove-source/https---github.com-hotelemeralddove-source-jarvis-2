# Credits & using open-source properly

This file exists because of one rule in this project:

> **We do not copy anybody's app. We build our own app and use open-source engines
> underneath it as backend libraries.**

There is a difference between *borrowing a library* and *Xerox-copying an app*. Arc Desk
does the first and never the second.

## What is ours (original work)

| Thing | Where |
|---|---|
| Arc Desk's whole UI — arc reactor painting, HUD cards, gauges, companion robot, console, setup dialog, themes, animations | `arcdesk/widgets/`, `arcdesk/theme.py` |
| The single-ticker performance architecture | `arcdesk/ticker.py` |
| Power modes, guards (fullscreen/battery throttle), settings, tray, autostart | `arcdesk/guard.py`, `config.py`, `tray.py`, `autostart.py` |
| The agent loop (think → tool → answer) and 21 automation tools | `arcdesk/ai/agent.py`, `tools.py` |
| ARC Lite, the offline rule-based brain | `arcdesk/ai/lite.py` |
| The voice daemon, wake/command state machine, loopback protocol | `arc_daemon.py`, `arcdesk/wake/` |
| ARC's persona and safety rules | `arcdesk/ai/persona.py` |

None of it is traced, decompiled, copied or re-skinned from another product. No Marvel
character, logo, or Iron Man/JARVIS asset is used — the reactor, the robot and the name ARC
are our own drawings and our own naming.

## What is borrowed (open-source engines, used as backend libraries)

| Library | Licence | What it does for us | Where it runs |
|---|---|---|---|
| **PySide6 / Qt** | LGPL-3.0 | windowing, painting, networking | in-app |
| **psutil** | BSD-3 | CPU/RAM/process data | in-app |
| **Vosk** (`vosk`) | Apache-2.0 | offline speech recognition | daemon process |
| **openWakeWord** (optional) | Apache-2.0 | pretrained wake-word detection | daemon process |
| **sounddevice** (or `pyaudio`) | MIT | microphone capture | daemon process |
| **Vosk small English model** | Apache-2.0 | the acoustic model file | daemon process |
| **MCP** (Model Context Protocol) | MIT | the tool-server protocol we speak | opt-in child processes |
| **Ollama / llama.cpp / LocalAI / vLLM / Jan / GPT4All / KoboldCpp / text-gen-webui** | MIT / Apache-2.0 / AGPL-3.0 — see `OPEN_SOURCE.md` | optional local model backends, detected over localhost | *their* processes, never ours |
| **Python stdlib** | PSF | HTTP, JSON, threads, subprocess | everywhere |

Using these is normal software engineering — the same way every app uses a JSON parser or a
TCP stack. Their licences are permissive and the attribution above satisfies them. What we do
**not** do: ship their example applications, their GUIs, or their icons as if they were ours.

Optional, if you want better tools later: `faster-whisper` (MIT) for accuracy, `pycaw` (MIT)
for exact Windows volume. Both are opt-in and both cost RAM — see `PERFORMANCE.md`.

## Why "we use open source" is not "we copied open source"

- We call APIs. Ollama, llama.cpp, Vosk and every MCP server run as **separate processes**.
  We never bundle their code, never copy their UI, never rebrand their app.
- The visible product — rector, HUD, charms, magic mode, console, agent loop, tools, daemon —
  is our own code, written in this repo.
- AGPL projects (Jan, KoboldCpp, text-generation-webui) are only ever *contacted over HTTP*,
  never linked into Arc Desk, which keeps their copyleft terms clean for you.

## If you fork or ship this

- Keep this file. Apache-2.0 requires attribution for Vosk/openWakeWord.
- Do not rebrand Marvel's JARVIS or use Marvel assets. "ARC" is our own name.
- If you put the daemon in a paid product, the Apache-2.0 parts stay Apache-2.0.


## Package catalogue

`arcdesk/ai/catalog.py` names 33 upstream projects without copying any of them: 32 open
source (MIT, Apache-2.0, BSD, AGPL-3.0, GPL-3.0, MPL-2.0) and one closed freeware listed
only so detection stays truthful. Arc Desk talks to them over localhost HTTP, a CLI or a
Python import. Licences and reasoning: `GITHUB.md` §7.
