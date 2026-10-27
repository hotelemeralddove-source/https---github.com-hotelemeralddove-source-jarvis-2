"""Image and video generation, with no invoice attached.

Truth first, because this is the area where assistants lie most:

* A **photoreal text-to-image model cannot run inside Arc Desk**. Stable Diffusion
  needs 4–8 GB of VRAM or a very slow CPU path, and loading it inside a 80 MB Qt
  app is exactly what the project promised never to do.
* So ARC talks to a **free local backend you run yourself** — Automatic1111 or
  ComfyUI — over localhost, the same rule as Ollama. Nothing is uploaded anywhere.
* When no backend is running, ARC still produces something real and free: a
  **poster** drawn with Pillow (gradient, geometry, typography) or the vector
  sketch engine, and **video** as a ken-burns pan/zoom over generated stills via
  ffmpeg. It says which one you got, every time, with the reason.

So "generate an image" has three honest tiers:

    tier 1  local diffusion backend   → real photoreal/diffusion image
    tier 2  offline poster / sketch   → real image, deliberately graphic
    tier 3  nothing available         → an instruction, not a fake result
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import shutil
import subprocess

from . import quiet
import time
import urllib.error
import urllib.request
from pathlib import Path

A1111 = "http://127.0.0.1:7860"
COMFY = "http://127.0.0.1:8188"

SETUP = (
    "Image generation needs a local backend (free, runs on your machine):\n"
    "  • Automatic1111 WebUI — start with `--api`, listens on 127.0.0.1:7860\n"
    "  • ComfyUI            — start normally, listens on 127.0.0.1:8188\n"
    "Then ask again. Nothing is uploaded; the picture is made on your own GPU/CPU."
)


def out_dir() -> Path:
    override = os.environ.get("ARCDESK_GEN_DIR", "").strip()
    if override:
        base = Path(os.path.expanduser(override))
        base.mkdir(parents=True, exist_ok=True)
        return base
    try:
        from . import config
        base = config.data_dir() / "generated"
    except Exception:
        base = Path.home() / "Pictures" / "ArcGen"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _post(url: str, payload: dict, timeout: float = 180) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _get(url: str, timeout: float = 3) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def backends() -> list[dict]:
    """Which free local image backends are actually answering right now."""
    found = []
    try:
        info = _get(f"{A1111}/sdapi/v1/options")
        found.append({"name": "Automatic1111", "url": A1111,
                      "model": (info or {}).get("sd_model_checkpoint", "unknown")})
    except Exception:
        pass
    try:
        stats = _get(f"{COMFY}/system_stats")
        found.append({"name": "ComfyUI", "url": COMFY,
                      "model": (stats.get("system", {}) or {}).get("comfyui_version", "")})
    except Exception:
        pass
    return found


def describe() -> str:
    found = backends()
    if found:
        return "image backend: " + ", ".join(f"{b['name']} ({b['url']})" for b in found)
    return ("no image backend running — I can still make offline posters and sketches. "
            + SETUP.replace("\n", " "))


# ------------------------------------------------------------------ tier 1
def _a1111(prompt: str, negative: str, width: int, height: int, steps: int,
           init: str = "", strength: float = 0.6, out: Path | None = None) -> str:
    payload = {
        "prompt": prompt, "negative_prompt": negative or
        "blurry, low quality, watermark, text artifacts, extra fingers",
        "width": int(width), "height": int(height), "steps": int(steps),
        "cfg_scale": 6.5, "sampler_name": "DPM++ 2M Karras",
    }
    endpoint = "txt2img"
    if init and Path(init).exists():
        with open(init, "rb") as fh:
            payload["init_images"] = [base64.b64encode(fh.read()).decode()]
        payload["denoising_strength"] = float(strength)
        endpoint = "img2img"
    data = _post(f"{A1111}/sdapi/v1/{endpoint}", payload)
    images = data.get("images") or []
    if not images:
        return "ERROR: the backend returned no image"
    raw = base64.b64decode(images[0].split(",", 1)[-1])
    target = out or (out_dir() / f"arc_{time.strftime('%Y%m%d_%H%M%S')}.png")
    target.write_bytes(raw)
    info = data.get("info") or "{}"
    try:
        seed = json.loads(info).get("seed")
    except Exception:
        seed = None
    return (f"{endpoint} image made with Automatic1111 → {target} "
            f"({width}×{height}, seed {seed}). It is on your machine only.")


def _comfy(prompt: str, negative: str, width: int, height: int, steps: int,
           ckpt: str = "", out: Path | None = None) -> str:
    """Minimal ComfyUI txt2img graph (SD1.5/SDXL checkpoint name required)."""
    ckpt = ckpt or os.environ.get("ARCDESK_SD_CKPT", "")
    if not ckpt:
        return ("ERROR: ComfyUI needs the checkpoint filename. Set "
                "ARCDESK_SD_CKPT=v1-5-pruned-emaonly.safetensors (or whatever your "
                "models folder holds) and try again.")
    graph = {
        "3": {"class_type": "KSampler",
              "inputs": {"seed": random.randint(1, 10**9), "steps": int(steps),
                         "cfg": 6.5, "sampler_name": "dpmpp_2m", "scheduler": "karras",
                         "denoise": 1.0, "model": ["4", 0], "positive": ["6", 0],
                         "negative": ["7", 0], "latent_image": ["5", 0]}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": int(width), "height": int(height), "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "arcdesk", "images": ["8", 0]}},
    }
    queued = _post(f"{COMFY}/prompt", {"prompt": graph})
    pid = queued.get("prompt_id")
    if not pid:
        return f"ERROR: ComfyUI rejected the graph: {str(queued)[:200]}"
    deadline = time.time() + 240
    while time.time() < deadline:
        time.sleep(2)
        try:
            hist = _get(f"{COMFY}/history/{pid}", timeout=6)
        except Exception:
            continue
        entry = (hist or {}).get(pid)
        if not entry:
            continue
        for node in (entry.get("outputs") or {}).values():
            for img in node.get("images") or []:
                url = (f"{COMFY}/view?filename={img['filename']}&subfolder="
                       f"{img.get('subfolder', '')}&type={img.get('type', 'output')}")
                target = out or (out_dir() / f"arc_{time.strftime('%Y%m%d_%H%M%S')}.png")
                with urllib.request.urlopen(url, timeout=30) as resp:
                    target.write_bytes(resp.read())
                return f"image made with ComfyUI → {target} ({width}×{height})"
    return "ERROR: ComfyUI did not finish within 4 minutes"


def image(prompt: str, width: int = 768, height: int = 768, steps: int = 24,
          negative: str = "", init_image: str = "", strength: float = 0.6,
          style: str = "") -> str:
    """Generate (or restyle, with `init_image`) — best available free tier."""
    prompt = _clean(prompt)
    if not prompt:
        return "ERROR: tell me what to draw"
    if style:
        prompt = f"{prompt}, {style}"
    found = backends()
    names = {b["name"] for b in found}
    try:
        if "Automatic1111" in names:
            return _a1111(prompt, negative, width, height, steps,
                          init_image, strength)
        if "ComfyUI" in names:
            return _comfy(prompt, negative, width, height, steps)
    except urllib.error.URLError as exc:
        return f"ERROR: backend went away ({exc.reason}). {SETUP}"
    except Exception as exc:
        return f"ERROR: generation failed ({type(exc).__name__}: {exc})"
    # tier 2 — offline, graphic, instant, honest
    note = ("(No diffusion backend is running, so this is an offline graphic "
            "poster, not a photo. Start Automatic1111 with --api for real images.)\n")
    if init_image:
        return note + _offline_restyle(init_image, prompt)
    return note + poster(prompt, width, height)


def _clean(prompt: str) -> str:
    return " ".join((prompt or "").strip().split())[:600]


# ------------------------------------------------------------------ tier 2
# colour words are the one prompt feature an offline generator can honour exactly
COLOURS = {
    "red": 0, "crimson": 350, "scarlet": 5, "orange": 25, "amber": 40, "gold": 45,
    "yellow": 55, "lime": 85, "green": 130, "emerald": 145, "teal": 175, "cyan": 185,
    "turquoise": 180, "blue": 215, "navy": 225, "indigo": 245, "purple": 275,
    "violet": 285, "magenta": 300, "pink": 330, "rose": 340, "brown": 25, "copper": 28,
}


def _colour_hues(prompt: str) -> list[int]:
    words = re.findall(r"[a-z]+", (prompt or "").lower())
    seen: list[int] = []
    for word in words:
        if word in COLOURS and COLOURS[word] not in seen:
            seen.append(COLOURS[word])
    return seen


def _palette(prompt: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Deterministic art direction from the words: same prompt, same colours.

    Named colours win (ask for gold and teal and you get gold and teal); otherwise
    the hue comes from a hash, so the same prompt is always the same picture.
    """
    import colorsys
    seed = int(hashlib.sha256(prompt.lower().encode()).hexdigest()[:8], 16)
    hues = _colour_hues(prompt)
    first = hues[0] if hues else seed % 360
    second = hues[1] if len(hues) > 1 else (first + 40) % 360
    top = colorsys.hsv_to_rgb((first % 360) / 360, 0.70, 0.52)
    bottom = colorsys.hsv_to_rgb((second % 360) / 360, 0.85, 0.28)
    return (tuple(int(c * 255) for c in top), tuple(int(c * 255) for c in bottom))


def poster(prompt: str, width: int = 768, height: int = 768,
           title: str = "", subtitle: str = "JARVIS DESK") -> str:
    """Offline generative graphic: gradient, geometry, typography. No model needed."""
    target = poster_path(prompt, width, height, title, subtitle)
    if target is None:
        return "ERROR: could not build the poster (is pillow installed?)"
    w, h = max(128, int(width)), max(128, int(height))
    return f"offline poster → {target} ({w}×{h}, palette from your words)"


def poster_path(prompt: str, width: int = 768, height: int = 768,
                title: str = "", subtitle: str = "JARVIS DESK") -> Path | None:
    """Same graphic, but returns the file so other code can use it (video stills)."""
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except Exception:
        return None
    prompt = _clean(prompt) or "arc reactor"
    w, h = max(128, int(width)), max(128, int(height))
    top, bottom = _palette(prompt)
    img = Image.new("RGB", (w, h), bottom)
    draw = ImageDraw.Draw(img)
    for y in range(h):                                    # vertical gradient
        t = y / max(1, h - 1)
        draw.line([(0, y), (w, y)],
                  fill=tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)))
    seed = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
    rnd = random.Random(seed)
    for _ in range(rnd.randint(5, 9)):                    # soft light discs
        r = rnd.randint(w // 12, w // 3)
        cx, cy = rnd.randint(0, w), rnd.randint(0, h)
        colour = tuple(min(255, c + rnd.randint(20, 70)) for c in top)
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r],
                                      fill=colour + (60,))
        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    img = img.filter(ImageFilter.GaussianBlur(max(1, w // 220)))

    # an arc-reactor motif: concentric rings drawn from the same seed, so the same
    # prompt always yields the same emblem
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ring = ImageDraw.Draw(layer)
    cx, cy = w * 0.5, h * 0.44
    accent = tuple(min(255, c + 150) for c in top)
    for i, frac in enumerate((0.30, 0.22, 0.13)):
        r = min(w, h) * frac
        ring.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent + (70 - i * 15,),
                     width=max(1, w // 320))
    import math as _math
    for step in range(24):                            # radial ticks
        angle = step * (2 * _math.pi / 24)
        r1, r2 = min(w, h) * 0.30, min(w, h) * 0.335
        ring.line([(cx + r1 * _math.cos(angle), cy + r1 * _math.sin(angle)),
                   (cx + r2 * _math.cos(angle), cy + r2 * _math.sin(angle))],
                  fill=accent + (80,), width=max(1, w // 400))
    img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")

    # typography: shrink until the longest word fits, then wrap; never overlap footer
    draw = ImageDraw.Draw(img)
    words = " ".join((title or prompt).split())[:80]
    footer_h = h * 0.12
    box_top, box_bottom = h * 0.16, h - footer_h
    box_h = box_bottom - box_top

    def wrap(size: int) -> tuple[list[str], object]:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
        except Exception:
            font = ImageFont.load_default()
        lines, line = [], ""
        for word in words.split():
            candidate = (line + " " + word).strip()
            if draw.textlength(candidate, font=font) > w * 0.84 and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        return lines, font

    big = max(14, int(min(w, h) * 0.14))
    for _ in range(40):
        lines, font = wrap(big)
        widest = max((draw.textlength(l, font=font) for l in lines), default=0)
        if widest <= w * 0.86 and len(lines) * big * 1.16 <= box_h:
            break
        big = int(big * 0.92)
    lines = lines[:4]
    block_h = len(lines) * big * 1.16
    y = box_top + (box_h - block_h) / 2
    for text_line in lines:
        tw = draw.textlength(text_line, font=font)
        draw.text(((w - tw) / 2 + 2, y + 2), text_line, font=font, fill=(0, 0, 0))
        draw.text(((w - tw) / 2, y), text_line, font=font, fill="#ffffff")
        y += big * 1.16

    try:
        small = ImageFont.truetype("DejaVuSans.ttf", max(11, int(big * 0.28)))
    except Exception:
        small = ImageFont.load_default()
    label = " ".join(subtitle.split())[:60]
    tw = draw.textlength(label, font=small)
    if tw > w * 0.9:
        label = label[:int(len(label) * w * 0.9 / tw)] + "…"
        tw = draw.textlength(label, font=small)
    draw.text(((w - tw) / 2, h - footer_h * 0.62), label, font=small,
              fill=tuple(min(255, c + 120) for c in top))

    stamp = time.strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha256(prompt.encode()).hexdigest()[:4]
    target = out_dir() / f"arc_poster_{stamp}_{digest}.png"
    img.save(target)
    return target


def _offline_restyle(source: str, prompt: str) -> str:
    """No diffusion: apply the words as a deterministic colour treatment."""
    try:
        from PIL import Image, ImageEnhance
    except Exception:
        return "ERROR: pillow is not installed"
    src = Path(os.path.expanduser(source))
    if not src.exists():
        return f"ERROR: no such image: {src}"
    img = Image.open(src).convert("RGB")
    top, bottom = _palette(prompt)
    tint = Image.new("RGB", img.size, top)
    blended = Image.blend(img, tint, 0.35)
    blended = ImageEnhance.Contrast(blended).enhance(1.15)
    target = out_dir() / f"arc_restyle_{time.strftime('%Y%m%d_%H%M%S')}.png"
    blended.save(target)
    return (f"offline restyle → {target} (the prompt chose the tint; a diffusion "
            f"backend would actually repaint it)")


# ------------------------------------------------------------------ video
def video(prompt: str, seconds: float = 4.0, width: int = 960, height: int = 540,
          frames: int = 3) -> str:
    """Video generation, honestly: AI clips need a backend, ken-burns does not.

    Tier 1 would be AnimateDiff/SVD inside ComfyUI. Tier 2 — what runs here — makes
    genuinely usable motion: several stills from the prompt, cross-faded with a slow
    pan and zoom. It is a real MP4 file, and it says how it was made.
    """
    exe = shutil.which("ffmpeg")
    if not exe:
        return ("ERROR: video needs ffmpeg (winget install Gyan.FFmpeg). "
                "For AI video, run ComfyUI with AnimateDiff and use image generation.")
    prompt = _clean(prompt) or "arc reactor"
    stills = []
    for i in range(max(2, min(6, int(frames)))):
        still = poster_path(f"{prompt} frame {i + 1}", width, height,
                            subtitle=f"JARVIS · {prompt[:24]}")
        if still and still.exists():
            stills.append(str(still))
    if not stills:
        return "ERROR: could not build the stills (is pillow installed?)"
    target = out_dir() / f"arc_video_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    per = max(1.0, float(seconds))
    cmd = [exe, "-y", "-v", "error"]
    for still in stills:
        cmd += ["-loop", "1", "-t", str(per), "-i", still]
    # slow zoom on each still, then concat with a short cross-fade
    filters = []
    for i in range(len(stills)):
        # d=1 keeps one output frame per input frame; `on` drives the zoom, so the
        # clip lasts exactly `per` seconds instead of per × d seconds.
        filters.append(
            f"[{i}:v]scale={width * 2}:-2,"
            f"zoompan=z='min(1+{0.18 / max(1, per * 25):.6f}*on,1.18)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps=25,format=yuv420p[v{i}]")
    chain = "".join(f"[v{i}]" for i in range(len(stills)))
    filters.append(f"{chain}concat=n={len(stills)}:v=1:a=0[out]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-crf", "24", "-movflags", "+faststart", str(target)]
    try:
        res = quiet.run(cmd, capture_output=True, text=True, timeout=300,
                             errors="replace")
    except Exception as exc:
        return f"ERROR: ffmpeg failed ({exc})"
    if res.returncode != 0 or not target.exists():
        tail = (res.stderr or "").strip().splitlines()[-2:]
        return "ERROR: ffmpeg could not build the clip — " + " | ".join(tail)
    return (f"offline motion clip → {target} "
            f"({target.stat().st_size / 1e6:.1f} MB, {len(stills)} stills, ken-burns "
            f"zoom). This is generated motion graphics, not AI video — for that, run "
            f"ComfyUI + AnimateDiff locally.")
