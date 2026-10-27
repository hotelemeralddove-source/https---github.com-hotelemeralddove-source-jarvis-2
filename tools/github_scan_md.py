"""Generate GITHUB.md from the catalogue, so the doc can never drift.

The catalogue in `arcdesk/ai/catalog.py` is the single source of truth. This
writer turns it into the document the user actually reads, which means a new
package appears in the docs the moment it appears in the code — no hand-edited
counts going stale.

    python tools/github_scan.py --md GITHUB.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk.ai.catalog import CATALOG, REFUSED, ROLES  # noqa: E402

INTRO = """# The GitHub stack — every open-source package ARC can use

**{total} packages. {oss} open source, 1 freeware (labelled). 0 of them cost money.
{wired} are already wired into Arc Desk.**

This is the answer to *"get the alternatives from GitHub"*. Two halves: the table of
projects, and the scanner that proves which ones are on **your** PC right now.

```bat
python tools\\github_scan.py            :: what is installed here
python tools\\github_scan.py --all      :: the whole catalogue
python tools\\github_scan.py --plan     :: paste-able commands for what is missing
python tools\\github_scan.py --json     :: machine readable
python tools\\github_scan.py --md GITHUB.md   :: regenerate this file
```

The catalogue is data, not code: `arcdesk/ai/catalog.py` imports nothing, opens no
socket and writes nothing. `tests/test_catalog.py` fails the build if a row gains a
price, a broken repo path, or a detector that does not exist.

Inside the app, ask ARC: **"what packages can read a PDF?"** or **"scan my GitHub
stack"** — the same catalogue answers, from the same file.

Legend: ⭐ = the one to pick if you have no opinion · ★ = Arc Desk drives it today.
"""

ROLE_ORDER = ("brain", "ears", "mouth", "wake", "see", "recall", "flow", "tools",
              "glue", "ship")

FOOTER = """
---

## What is *not* in the list, and why

Refusing is a feature, and the reasons are written down instead of quietly omitted:

{refusals}

## The honest caveats

* **Open source ≠ free of obligations.** AGPL projects (Jan, KoboldCpp, Aphrodite,
  text-generation-webui, YOLO, Skyvern) are free to *use*, and Arc Desk only sends
  HTTP requests to them. If you modify one and publish the result, its licence
  follows your code.
* **Model weights are a separate licence from the code.** Qwen and Mistral weights
  (Apache-2.0) are genuinely unrestricted. Llama weights carry a usage policy. Gemma
  weights carry Google's terms. Arc Desk never bundles weights — you pull them.
* **A closed app can still be useful.** LM Studio is listed because honesty beats
  tidiness: it is free to use, it is not open source, and detection says so.
* **Nothing here is vendored.** No third-party source code is copied into Arc Desk;
  every project is reached over a port, a CLI, or a normal import (see `CREDITS.md`).

## How Arc Desk chooses

1. **Fewest moving parts that still work offline.** That is why Vosk + Windows SAPI
   ship by default: two small pieces, no PyTorch, no service to babysit.
2. **Biggest upgrade per megabyte of RAM.** sherpa-onnx replaces ears, mouth and wake
   word with one Apache-2.0 runtime — the single best upgrade available.
3. **Nothing that needs an account to start.** Porcupine's free tier needs a Picovoice
   AccessKey, so openWakeWord gets the job instead.
4. **Never a paid default.** The cost guard (`arcdesk/ai/cost.py`) classifies every
   brain LOCAL and blocks anything metered until you opt in twice.
"""

PICK = {"ollama", "llamacpp", "vosk", "sherpa", "piper", "openwakeword", "tesseract",
        "chroma", "ffmpeg", "markitdown"}


def _row(p) -> str:
    star = " ⭐" if p.key in PICK else ""
    wired = " ★" if p.arc_uses else ""
    repo = f"`{p.repo}`" if p.repo else "*(closed source)*"
    note = p.note.replace("|", "\\|")
    return f"| **{p.name}**{star}{wired} | {repo} | {p.licence} | {p.job}. {note} |"


def write_markdown(path: str | Path) -> Path:
    wired = sum(1 for p in CATALOG if p.arc_uses)
    oss = sum(1 for p in CATALOG if p.is_open_source)
    out = [INTRO.format(total=len(CATALOG), oss=oss, wired=wired)]

    for role in ROLE_ORDER:
        group = [p for p in CATALOG if p.role == role]
        if not group:
            continue
        out.append(f"\n## {role.title()} — {len(group)} projects  \n*{ROLES.get(role, '')}*\n")
        out.append("| Project | GitHub | Licence | What it does for ARC |")
        out.append("|---|---|---|---|")
        out.extend(_row(p) for p in group)
        out.append("")

    refusals = "\n".join(f"* **{name}** — {why}" for name, why in REFUSED)
    out.append(FOOTER.format(refusals=refusals))

    target = Path(path)
    target.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return target.resolve()


if __name__ == "__main__":
    print(write_markdown(sys.argv[1] if len(sys.argv) > 1 else "GITHUB.md"))
