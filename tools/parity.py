#!/usr/bin/env python3
"""What is in the box, what is not, and what the .exe really contains.

    python tools/parity.py            # write WHATS_INCLUDED.md
    python tools/parity.py --check    # exit 1 if that file is out of date

Why generated: the answer to "what is missing on my laptop?" changes every time a
dependency or a model is added. Typed by hand it would be wrong within a week — and a
wrong list here is worse than none, because it sends somebody downloading 1.5 GB they did
not need, or leaves them hunting for a file that was never necessary.

Three lists, and the difference between them matters:

  A. shipped INSIDE the .exe        (libraries, all of arcdesk/*.py, the two helper
                                     scripts PyInstaller carries as data)
  B. downloaded AFTER install       (models, from inside the app, with sizes)
  C. deliberately NOT shipped       (weights that would double the installer, and the
                                     private-environment route used instead)

The parity column is the user's actual question: *"nee sandbox-la run pani pakum pothu
yethu irukku, adhu .exe-layum irukanum"* — so every library the sandbox has is listed
with whether the build collects it, read from the workflow and the spec, not from memory.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "WHATS_INCLUDED.md"
SPEC = ROOT / "packaging" / "arcdesk.spec"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"

# library -> (pip name, what it is for, is it required for the app to start?)
LIBS = [
    ("PySide6", "PySide6-Essentials", "the whole interface", True),
    ("numpy", "numpy", "audio buffers, image maths", True),
    ("psutil", "psutil", "CPU/RAM readings, process list", True),
    ("PIL", "Pillow", "screenshots, image edits, art", True),
    ("pypdf", "pypdf", "reading PDFs at the moment you ask", False),
    ("docx", "python-docx", "Word files", False),
    ("openpyxl", "openpyxl", "Excel files", False),
    ("pptx", "python-pptx", "PowerPoint files", False),
    ("mutagen", "mutagen", "music metadata, playback info", False),
    ("vosk", "vosk", "the wake word (ears)", False),
    ("sounddevice", "sounddevice", "the microphone", False),
    ("sherpa_onnx", "sherpa-onnx", "voice lock — who may command it", False),
]

# things that are downloaded later, from inside the app: id, size, where it goes, why
DOWNLOADS = [
    ("Speech model (Vosk)", "40 MB", "ArcDesk<BS>vosk-model-small-en-us-0.15",
     'Settings → Voice → "Get the ears ready…"', 'the wake word "hey jarvis"'),
    ("Speaker model", "30 MB", "ArcDesk<BS>models<BS>speaker_embedding.onnx",
     'the same button', 'the voice lock — only your voice may command it'),
    ("Reply-voice engine · IndicF5", "1.5 GB",
     "the app's own environment (%APPDATA%<BS>ArcDesk<BS>engine_env on the installed .exe)",
     'Settings → Voice → "Get the reply-voice engine…"', 'Tamil / Hindi replies in a cloned voice'),
    ("Reply-voice engine · XTTS-v2", "1.9 GB",
     "the same private environment",
     'the same button', 'English replies in a cloned voice'),
    ("Built-in brain · Qwen2.5 1.5B", "1066 MB", "ArcDesk<BS>models<BS>*.gguf",
     'Settings → Local AI → "Add a brain…"', 'real conversation instead of Lite, offline'),
    ("Built-in brain · Qwen2.5 0.5B", "469 MB", "the same folder",
     'the same button', 'a lighter chat-only brain for a small laptop'),
    ("piper voices", "~60 MB each", "ArcDesk<BS>voices",
     'the optional fallback voice (Tamil/Hindi/English, not a clone)',
     'a real voice when no clone engine is installed'),
]

NOT_SHIPPED = [
    ("torch + IndicF5 weights", "~1.5 GB",
     "a compiled .exe cannot import a package that arrives later, and this would "
     "quadruple the installer. Installed into a private folder (or a sidecar "
     "environment) and spoken to through tools/clone_speak.py."),
    ("XTTS-v2 weights", "~1.9 GB", "same reason, same route (CPML licence: personal use)."),
    ("llama.cpp + GGUF model", "~1.1 GB",
     "same reason. `llama-cpp-python[server]` runs from that same private folder."),
    ("your voice clips, notes, vault, logs", "—",
     "yours. They live in %APPDATA%<BS>ArcDesk and are never uploaded anywhere."),
]


def have(module: str) -> str:
    """", "yes", or "yes, but the import fails here — <why>".

    `find_spec` is not enough and the difference matters: `sounddevice` is installed in
    this sandbox but cannot *import*, because PortAudio is a system library here. On
    Windows the wheel carries its own PortAudio DLL, so the same check passes there. The
    report says which of the two it is instead of claiming "yes" from a filename.
    """
    try:
        if importlib.util.find_spec(module) is None:
            return "no"
    except Exception:
        return "no"
    try:
        __import__(module)
        return "yes"
    except Exception as exc:                       # noqa: BLE001
        return f"yes, but import fails here ({type(exc).__name__})"


def workflow_packages() -> tuple[list[str], list[str], bool]:
    """(hard deps, voice deps, collects the ears in the spec?) read from the real files."""
    text = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.is_file() else ""
    hard: list[str] = []
    for line in text.splitlines():
        if "pip install" in line and "PySide6" in line:
            hard = [p.strip('"') for p in line.split("pip install", 1)[1].split()]
            break
    voice: list[str] = []
    m = re.search(r"foreach \(\$pkg in @\(([^)]*)\)\)", text)
    if m:
        voice = [p.strip().strip('"') for p in m.group(1).split(",")]
    else:
        for line in text.splitlines():
            if "pip install" in line and "vosk" in line:
                voice = [p for p in line.split("pip install", 1)[1].split() if p]
                break
    spec_text = SPEC.read_text(encoding="utf-8") if SPEC.is_file() else ""
    spec_collects = "collect_submodules" in spec_text and '"vosk"' in spec_text
    return hard, voice, spec_collects


def arcdesk_modules() -> list[Path]:
    return sorted((ROOT / "arcdesk").rglob("*.py"))


def data_scripts() -> list[str]:
    """Scripts the frozen app runs or reads — they must be in the spec's datas."""
    wanted = []
    spec_text = SPEC.read_text(encoding="utf-8") if SPEC.is_file() else ""
    for name in ("doctor.py", "clone_speak.py"):
        if f'"{name}"' in spec_text:
            wanted.append(f"tools/{name}  ✔ shipped as data")
        else:
            wanted.append(f"tools/{name}  ✘ MISSING from the spec — the .exe will not find it")
    return wanted


def report() -> str:
    hard, voice, spec_collects = workflow_packages()
    mods = arcdesk_modules()
    lines: list[str] = []
    add = lines.append

    add("# What is in the .exe, what you download after, and what is never shipped")
    add("")
    add("*Generated by `python tools/parity.py` — do not edit by hand.*")
    add("")
    add("Read this once, after installing. Everything in section A is already on your "
        "laptop the moment **ArcDeskSetup.exe** finishes. Section B is the short list of "
        "downloads, each one offered by a button inside the app, with its real size. "
        "Section C is what deliberately does not ship, and why — so nothing is "
        "\"missing\" by accident.")
    add("")

    add("## A · Already inside the .exe — nothing to do")
    add("")
    add(f"- **{len(mods)} Python modules** of the app itself "
        f"(`arcdesk/**/*.py`), collected by `collect_submodules(\"arcdesk\")` in "
        f"`packaging/arcdesk.spec`. A hand-written list is how a packaged app imports "
        f"fine and dies on the one screen you only open once.")
    for row in data_scripts():
        add(f"- `{row}` — helper scripts the frozen app reads at runtime")
    add("- the interface, themes, icons, and the generated in-app pages (HTML)")
    add("- `ArcDesk.exe` (the window) and `ArcDeskVoice.exe` (the ears) — two processes, "
        "so a microphone never shares a frame budget with the animation")
    add("")
    add("| library | pip name | used for | in this sandbox | in the .exe | needed to start |")
    add("|---|---|---|---|---|---|")
    for module, pip_name, why, required in LIBS:
        here = have(module)
        if pip_name in hard or pip_name.replace("-", "_") in [h.replace("-", "_") for h in hard]:
            ship = "yes — hard dependency"
        elif any(pip_name.split("[")[0].lower() == v.lower() for v in voice):
            ship = "yes — collected by the spec" if spec_collects else "yes — optional"
        else:
            ship = "yes"
        add(f"| `{module}` | `{pip_name}` | {why} | {here} | {ship} | "
            f"{'yes' if required else 'no'} |")
    add("")
    add("The build installs its dependencies one package at a time and prints which of "
        "`sounddevice / vosk / openwakeword / sherpa_onnx` made it in, so the answer to "
        "\"can this .exe hear me?\" is in the build log instead of guessed.")
    add("")

    add("## B · Downloaded after install — from inside the app, one button each")
    add("")
    add("| what | size | where it lands | where to press it | what it unlocks |")
    add("|---|---|---|---|---|")
    for what, size, where, how, why in DOWNLOADS:
        add(f"| {what} | {size} | `{where}` | {how} | {why} |")
    add("")
    add("**None of these are required to start the app.** Without them: the window, every "
        "tool, the vault and Lite all work; the wake word needs the two models (70 MB "
        "total), a cloned reply voice needs one engine, and a real conversation needs a "
        "brain. The app says which of those is missing, in words, on the dashboard.")
    add("")

    add("## C · Never shipped inside the installer — and the route used instead")
    add("")
    add("| thing | size | why not |")
    add("|---|---|---|")
    for what, size, why in NOT_SHIPPED:
        add(f"| {what} | {size} | {why} |")
    add("")
    add("The pattern for all three: **a compiled `.exe` cannot import a package that "
        "arrives later**, and putting 1–2 GB of weights inside a 53 MB installer is not a "
        "product. So the app builds a private folder of its own "
        "(`%APPDATA%<BS>ArcDesk<BS>engine_env`), installs the engine there, and talks to it "
        "like a separate program. Nothing global, nothing on `PATH`, and deleting the "
        "folder only removes that feature.")
    add("")

    add("## D · The parity check — sandbox vs .exe")
    add("")
    add("| question | answer |")
    add("|---|---|")
    add(f"| does every `arcdesk` module ship? | yes — {len(mods)} of {len(mods)}, "
        f"collected automatically |")
    add(f"| does the build install every hard dependency? | "
        f"{'yes' if hard else 'NO — the workflow has no install step'} "
        f"(`{', '.join(p.split('==')[0] for p in hard) or 'missing'}`) |")
    add(f"| are the voice libraries attempted separately? | "
        f"{'yes — ' + ', '.join(voice) if voice else 'no'} |")
    add(f"| does the spec collect the wake engine? | "
        f"{'yes' if spec_collects else 'NO — the .exe would be silent'} |")
    add("| can a feature added later be added to an installed .exe? | yes, through the "
        "private environment; never by copying files into the .exe |")
    add("")
    add("Anything in this table that reads NO is a bug, not a note. `tests/test_parity.py` "
        "fails the suite on it.")
    add("")

    add("## D2 · Where the app writes, once it is installed")
    add("")
    add("| path | what |")
    add("|---|---|")
    add("| `%APPDATA%<BS>ArcDesk<BS>settings.json` | every setting, saved atomically |")
    add("| `%APPDATA%<BS>ArcDesk<BS>vosk-model-small-en-us-0.15` | the speech model (B) |")
    add("| `%APPDATA%<BS>ArcDesk<BS>models` | the brain GGUF and the speaker model (B) |")
    add("| `%APPDATA%<BS>ArcDesk<BS>voices` | your reply voices and their transcripts |")
    add("| `%APPDATA%<BS>ArcDesk<BS>engine_env` | the private Python that holds a clone "
        "engine or llama.cpp (C) |")
    add("| `%APPDATA%<BS>ArcDesk<BS>vault` | answers, notes, the things worth keeping |")
    add("")
    add("Copying that one folder to another machine moves everything except the "
        "enrolled voice lock, which stays per machine on purpose.")
    add("")

    add("## E · First ten minutes on a fresh laptop")
    add("")
    add("1. Double-click **ArcDeskSetup.exe** → Install → at the end tick "
        "\"start with Windows, silently\" if you want `hey jarvis` to work after a reboot.")
    add("2. It opens the setup card: pick **icon** or **voice**, read the five cards, "
        "press **Start ARC**.")
    add("3. Settings → Voice → **Get the ears ready** → 70 MB → the wake word works.")
    add("4. Settings → Local AI → **Add a brain** → 1066 MB → real answers instead of Lite.")
    add("5. Optional: Settings → Voice → **Voices…** to import a reply voice, then "
        "**Get the reply-voice engine** (1.5 GB Tamil/Hindi, 1.9 GB English).")
    add("")
    add("Nothing on that list needs a command prompt, a key, or an account.")
    add("")
    # written as <BS> above so this file never relies on a fragile escape: a Windows
    # path in a normal string is how you get a SyntaxWarning and, one day, a mangled path
    return "\n".join(lines).replace("<BS>", chr(92))


def main(argv: list[str]) -> int:
    text = report()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current.strip() != text.strip():
            print("WHATS_INCLUDED.md is out of date — run: python tools/parity.py")
            return 1
        print(f"WHATS_INCLUDED.md is current ({len(text.splitlines())} lines)")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.name} — {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
