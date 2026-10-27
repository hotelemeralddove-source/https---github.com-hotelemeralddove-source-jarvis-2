"""Think first, then do it — a tiny deterministic planner.

The user's sentence is turned into an ordered list of tool calls, the list is shown
("here is what I am about to do"), and only then executed. Two reasons it is rules and
not a language model:

* **Speed.** A plan is built in microseconds, so "play X" never waits for a model.
* **Honesty.** You can read every recipe in this file. If none matches, ARC says what it
  *can* chain instead of improvising a five-step plan that half-works.

A recipe is a regex plus a function that returns ``[(tool, args, note), ...]``.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

MAX_STEPS = 6

_PATH_HINT = re.compile(
    r"(?P<q>\"[^\"]+\")|(?P<p>(?:[A-Za-z]:\\|~/|/)[^\s\"']+)"
    r"|(?P<n>[^\s\"']+\.(?:mp3|m4a|flac|wav|ogg|opus|mp4|mkv|mov|avi|webm|png|jpe?g|"
    r"webp|pdf|docx?|xlsx?|pptx?|csv|json|txt|md|srt))", re.I)


def files_in(text: str) -> list[str]:
    out, seen = [], set()
    for match in _PATH_HINT.finditer(text or ""):
        raw = (match.group("q") or match.group("p") or match.group("n") or "").strip()
        raw = raw.strip('"').rstrip(".,;:")
        if raw and raw not in seen:
            seen.add(raw)
            out.append(raw)
    return out


def drive_words(text: str) -> str:
    """Find something that looks like a drive: 'D:', 'E drive', 'pen drive', 'Seagate'."""
    match = (re.search(r"\b([A-Za-z]):\\", text)
             or re.search(r"\b([A-Za-z])\s+(?:drive|disk|hard ?disk)\b", text, re.I))
    if match:
        return f"{match.group(1).upper()}:\\"
    return ""


_EXTERNAL = re.compile(r"\b(external|removable|usb|pen ?drive|flash ?drive|hard ?disk|"
                       r"hard ?drive|portable|memory card|sd card)\b", re.I)


def external_roots() -> list[str]:
    from . import library
    flag = [d for d in library.drives() if d.get("removable")]
    return [d["path"] for d in (flag or library.drives())]


def _scan_steps(text: str) -> list[tuple[str, dict, str]]:
    roots = drive_words(text)
    wanted_external = bool(_EXTERNAL.search(text))
    if wanted_external and not roots:
        found = external_roots()
        if not found:
            # No external disk is attached. Rescanning the default folders here would
            # quietly throw away a good index, so report what is actually plugged in.
            return [("library", {"action": "drives"},
                     "no external disk is attached — showing the drives I can see")]
        roots = "|".join(found)
    args: dict = {"action": "scan"}
    if roots:
        args["roots"] = roots
    note = ("scanning the external disk, read-only" if roots
            else "scanning your music and video folders")
    return [("library", args, note)]


def _play_steps(text: str, kind: str = "") -> list[tuple[str, dict, str]]:
    # keep only what comes after the play verb: "scan my disk and play X" -> "X"
    tail = text
    match = re.search(r"\b(?:play|put on|start playing|podu|podunga|kaattu|kelu|"
                      r"play pann?u)\b", text, re.I)
    if match:
        tail = text[match.end():]
    remainder = re.sub(
        r"^\s*(?:arc[ ,]*)?(?:please\s+)?(?:can you\s+)?(?:me\s+)?(?:the\s+)?", "", tail,
        flags=re.I)
    remainder = re.sub(r"\b(?:the\s+)?(?:song|music|video|track|paatu|padal)\b\s*", " ",
                       remainder, flags=re.I)
    remainder = re.sub(r"\b(?:from|on)\s+(?:my\s+)?(?:external|removable|usb|pen)\s+"
                       r"(?:drive|disk|hard ?disk)\b", " ", remainder, flags=re.I)
    query = " ".join(remainder.split()).strip(" .")
    if not query:
        query = "latest"
    return [("play", {"query": query, "kind": kind}, f"finding and playing “{query}”")]


def _reel_steps(text: str) -> list[tuple[str, dict, str]]:
    files = files_in(text)
    if len(files) < 1:
        return []
    template = ("cinematic_teaser" if re.search(r"teaser", text, re.I) else
                "story" if re.search(r"story|status", text, re.I) else
                "slideshow" if re.search(r"slideshow|photos?", text, re.I) else
                "hotel_tour" if re.search(r"hotel|resort", text, re.I) else
                "reel_hook")
    title = ""
    match = re.search(r"(?:titled|called|title)\s+[\"']?([^\"']{2,70})", text, re.I)
    if match:
        title = match.group(1).strip(" .")
    return [("video_studio", {"action": "template", "clips": "|".join(files),
                              "template": template, "title": title},
             f"building a {template} from {len(files)} clip(s)")]


def think(request: str) -> dict:
    """Return {'goal', 'steps': [(tool, args, note)], 'kind'} — no side effects."""
    text = (request or "").strip()
    low = text.lower()
    steps: list[tuple[str, dict, str]] = []
    kind = "unknown"

    if not text:
        return {"goal": "", "steps": [], "kind": "empty"}

    wants_scan = bool(_EXTERNAL.search(low) or re.search(r"\bscan\b", low))
    wants_play = bool(re.search(r"\b(play|podu|kaattu|kelu|put on)\b", low))

    if wants_scan and wants_play:
        steps = _scan_steps(text) + _play_steps(text, "audio" if "song" in low else "")
        kind = "scan_then_play"
    elif wants_play:
        video = bool(re.search(r"\b(video|movie|film|padam)\b", low))
        steps = _play_steps(text, "video" if video else "audio")
        kind = "play"
    elif wants_scan:
        steps = _scan_steps(text)
        kind = "scan"
    elif re.search(r"\b(reel|teaser|slideshow|montage|story video)\b", low) and files_in(text):
        steps = _reel_steps(text)
        kind = "reel"
    elif files_in(text) and re.search(r"\b(grade|look|cinematic|noir|vintage)\b", low):
        target = files_in(text)[0]
        look = next((name for name in ("cinematic", "noir", "vintage", "cyberpunk")
                     if name in low), "cinematic")
        tool = "video_studio" if target.lower().endswith(
            (".mp4", ".mkv", ".mov", ".avi", ".webm")) else "image_studio"
        steps = [(tool, {"action": "look", "path": target, "look": look},
                  f"{look} grade on {Path(target).name}")]
        kind = "grade"
    elif files_in(text) and re.search(r"\b(review|summarise|summarize|explain|read)\b", low):
        target = files_in(text)[0]
        mode = "review" if "review" in low else "summary"
        steps = [("read_file", {"path": target, "mode": mode},
                  f"reading {Path(target).name}")]
        kind = "read"
    elif files_in(text) and re.search(r"\b(analyse|analyze|mine|report)\b", low):
        steps = [("mine", {"action": "report", "path": files_in(text)[0]},
                  "measuring the data")]
        kind = "analyse"
    elif re.search(r"\b(should i|help me decide|decide between|which is better|"
                   r"confused)\b", low):
        steps = [("coach", {"mode": "decide", "text": text}, "thinking it through with you")]
        kind = "decide"
    elif re.search(r"\b(i want to|my goal|help me plan|plan for me|how do i start)\b", low):
        steps = [("coach", {"mode": "plan", "text": text}, "turning it into a 7-day plan")]
        kind = "plan"
    elif re.search(r"\b(slow|laptop|pc|computer|ram|cpu|disk space|hang)\b", low) and \
            re.search(r"\b(check|why|clean|fix|status)\b", low):
        steps = [("system_report", {}, "measuring this machine"),
                 ("running_apps", {}, "listing what is using the memory")]
        kind = "diagnose"
    elif re.search(r"\b(what.?s on|today|schedule|agenda|briefing)\b", low):
        steps = [("briefing", {"what": "today"}, "gathering today, from real sources")]
        kind = "briefing"

    return {"goal": text, "steps": steps[:MAX_STEPS], "kind": kind}


def describe_plan(plan: dict) -> str:
    if not plan["steps"]:
        return ""
    lines = [f"Plan ({len(plan['steps'])} step{'s' if len(plan['steps']) > 1 else ''}):"]
    for index, (tool, args, note) in enumerate(plan["steps"], 1):
        detail = ", ".join(f"{k}={v}" for k, v in args.items()
                           if k in ("query", "kind", "roots", "path", "template", "mode"))
        lines.append(f"  {index}. {note}  [{tool}{' ' + detail if detail else ''}]")
    return "\n".join(lines)


def run(request: str, confirm: bool = True, verbose: bool = True) -> str:
    """Build the plan and execute it, step by step, stopping at the first error."""
    from .ai import tools as tool_layer

    plan = think(request)
    if not plan["steps"]:
        return ("I could not turn that into steps I trust. I can chain: scan a disk, "
                "play a song or video, build a reel, grade an image, read/analyse a file, "
                "decide between options, or plan a goal.")

    guarded = [s for s in plan["steps"] if tool_layer.TOOLS.get(s[0])
               and tool_layer.TOOLS[s[0]].confirm]
    if guarded and not confirm:
        return describe_plan(plan) + "\nThis needs your ok before I run it."

    started = time.time()
    outputs: list[str] = []
    failed = False
    for index, (tool, args, note) in enumerate(plan["steps"], 1):
        step_started = time.time()
        try:
            result = tool_layer.call(tool, args)
        except Exception as exc:                       # call() should not raise
            result = f"ERROR: {type(exc).__name__}: {exc}"
        ms = (time.time() - step_started) * 1000
        outputs.append(result)
        if str(result).startswith("ERROR"):
            failed = True
            if verbose:
                outputs.insert(0, f"step {index} ({note}) failed — stopping there.")
            break
        if verbose:
            outputs.insert(len(outputs) - 1, f"✓ {index}. {note} ({ms:.0f} ms)")

    total = (time.time() - started) * 1000
    head = describe_plan(plan) if verbose else ""
    tail = f"— {total:.0f} ms total" + (" · stopped early" if failed else "")
    body = "\n".join(outputs)
    return (head + "\n" + body + "\n" + tail).strip()


def recipes() -> str:
    """What this planner can chain, in plain words."""
    return ("I can chain these:\n"
            "  · scan my music / scan my external disk\n"
            "  · play <song> · play <video> · play <song> from my pen drive\n"
            "  · scan my external disk and play <song>\n"
            "  · make a reel / teaser / slideshow from <files>\n"
            "  · put a cinematic look on <file>\n"
            "  · read / review / analyse <file>\n"
            "  · help me decide <question> · plan <goal>\n"
            "  · check my pc · what's on today")
