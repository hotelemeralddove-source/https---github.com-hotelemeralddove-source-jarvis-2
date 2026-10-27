"""The studio — advanced video, audio and image work, all local and free.

`editing.py` changes *one file with one operation*. This module makes **things**:
a reel out of six clips with cross-fades and a caption, a podcast mix with the music
ducking under the voice, an Instagram story card, a contact sheet, a colour-graded
teaser. Everything runs on ffmpeg and Pillow that are already on the machine — no
upload, no account, no per-minute bill.

Three rules carried over from the rest of Arc Desk:

* **Nothing is overwritten.** Compositions and generated assets land in
  ``<data>/studio/`` with a timestamp; single-file looks write a sibling.
* **No invented media.** Ask for music and it will *not* synthesise a track: it says
  where to put the file. Ask for captions and it will not invent words.
* **No hidden magic.** Every template is a plain dict you can read in this file, and
  `catalog()` prints exactly what each one does.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from . import quiet
import time
from pathlib import Path

from . import editing

# --------------------------------------------------------------------- shared
ASPECTS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),      # reels, shorts, status
    "4:5": (1080, 1350),       # instagram feed
    "1:1": (1080, 1080),       # square post
    "16:9": (1920, 1080),      # youtube, desktop
    "4:3": (1440, 1080),       # classic
    "21:9": (2560, 1080),      # cinematic
}

# xfade transition names that exist in ffmpeg 5+ ("" = hard cut)
TRANSITIONS: dict[str, str] = {
    "cut": "",
    "fade": "fade",
    "fade_black": "fadeblack",
    "fade_white": "fadewhite",
    "dissolve": "dissolve",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "wipe_up": "wipeup",
    "wipe_down": "wipedown",
    "slide_left": "slideleft",
    "slide_right": "slideright",
    "slide_up": "slideup",
    "slide_down": "slidedown",
    "circle_open": "circleopen",
    "circle_close": "circleclose",
    "radial": "radial",
    "smooth_left": "smoothleft",
    "smooth_right": "smoothright",
    "diag_tl": "diagtl",
    "diag_br": "diagbr",
    "pixelize": "pixelize",
    "hblur": "hblur",
    "zoomin": "zoomin",
    "squeeze_v": "squeezev",
    "cover_left": "coverleft",
    "reveal_up": "revealup",
}

# one-pass looks: name -> ffmpeg filter chain
VIDEO_LOOKS: dict[str, str] = {
    "none": "",
    "cinematic": "curves=preset=strong_contrast,colorbalance=rs=-0.06:gs=-0.01:bs=0.10:"
                 "rm=0.04:bm=-0.03:rh=0.06:bh=-0.06,eq=saturation=1.06",
    "teal_orange": "colorbalance=rs=-0.10:bs=0.16:rm=0.02:rh=0.12:bh=-0.14,"
                   "eq=saturation=1.18:contrast=1.06",
    "warm": "colorbalance=rs=0.08:gs=0.02:bs=-0.08,eq=saturation=1.04",
    "cool": "colorbalance=rs=-0.08:gs=0.0:bs=0.10,eq=saturation=0.96",
    "noir": "format=gray,eq=contrast=1.28:brightness=-0.03,vignette=PI/4.5,"
            "noise=alls=6:allf=t",
    "mono_soft": "format=gray,eq=contrast=0.95:brightness=0.02",
    "vintage": "curves=preset=vintage,eq=saturation=0.86:contrast=0.98,"
               "vignette=PI/5,noise=alls=7:allf=t",
    "cyberpunk": "eq=saturation=1.45:contrast=1.1,colorbalance=rs=0.14:bs=0.18:"
                 "rm=0.05:bm=0.05,unsharp=5:5:0.7",
    "vhs": "noise=alls=12:allf=t,chromashift=cbh=3:crh=-3,eq=saturation=1.2:"
           "contrast=1.05,curves=preset=lighter",
    "dream": "split[a][b];[b]gblur=sigma=8[bl];[a][bl]blend=all_mode=screen:all_opacity=0.35",
    "grain": "noise=alls=10:allf=t",       # note: film grain barely compresses
    "sharp": "unsharp=5:5:1.1:5:5:0.0",
    "soft": "gblur=sigma=1.6",
    "vignette": "vignette=PI/4",
    "letterbox": "drawbox=x=0:y=0:w=iw:h=ih*0.09:color=black:t=fill,"
                 "drawbox=x=0:y=ih*0.91:w=iw:h=ih*0.09:color=black:t=fill",
    "slowmo": "setpts=2.0*PTS,minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc",
}

# name -> (aspect, default transition, look, target seconds, note)
VIDEO_TEMPLATES: dict[str, dict] = {
    "reel_hook": {"aspect": "9:16", "transition": "wipe_left", "look": "cinematic",
                  "seconds": 30, "title": "top third",
                  "note": "short vertical reel: hook in the first 2 s, caption top third"},
    "story": {"aspect": "9:16", "transition": "fade", "look": "warm", "seconds": 15,
              "note": "status/story length, safe margins for reply box"},
    "product_ad": {"aspect": "4:5", "transition": "zoomin", "look": "teal_orange",
                   "seconds": 20, "note": "feed ad: product close-ups, price end card"},
    "hotel_tour": {"aspect": "16:9", "transition": "smooth_left", "look": "warm",
                   "seconds": 60, "title": "room name",
                   "note": "walkthrough with room captions"},
    "travel_vlog": {"aspect": "16:9", "transition": "dissolve", "look": "cinematic",
                    "seconds": 90, "note": "long cut with dissolves between places"},
    "tutorial": {"aspect": "16:9", "transition": "cut", "look": "sharp", "seconds": 300,
                 "note": "screen recording: no fancy transition, legibility first"},
    "testimonial": {"aspect": "1:1", "transition": "fade_black", "look": "soft",
                    "seconds": 45, "note": "talking head, square, gentle fades"},
    "cinematic_teaser": {"aspect": "21:9", "transition": "fade_black", "look": "noir",
                         "seconds": 20, "title": "big serif title",
                         "note": "letterboxed teaser, hard cuts on beat"},
    "slideshow": {"aspect": "16:9", "transition": "fade", "look": "cinematic",
                  "seconds": 30, "note": "still images with a slow ken-burns push"},
    "whatsapp_status": {"aspect": "9:16", "transition": "cut", "look": "warm",
                        "seconds": 30, "note": "30 s limit, no music licensing risk"},
}

AUDIO_OPS: dict[str, str] = {
    "denoise": "spectral noise reduction (afftdn) + 80 Hz high-pass — hiss, fan, room tone",
    "deess": "tame 'sss' on voice (deesser)",
    "gate": "noise gate: silence between phrases, no breathing (agate)",
    "compress": "even out loud/quiet delivery (acompressor)",
    "eq3": "3-band tone: bass / mid / treble in dB (equalizer)",
    "reverb": "small room / hall tail (aecho)",
    "loudnorm": "broadcast loudness, -14 LUFS for social or -16 for podcast",
    "fade": "fade in and out",
    "trim": "cut a start/end window",
    "speed": "tempo change without pitch shift (atempo)",
    "mono": "fold to mono",
    "stereo_width": "widen the stereo image (extrastereo)",
    "silence_trim": "cut leading/trailing silence",
    "chapters": "print the timecodes where speech starts (silencedetect)",
    "waveform": "render a PNG waveform you can put on a video",
    "mix": "mix several tracks with per-track gain",
    "duck": "music under voice: sidechain compression",
}

IMAGE_LOOKS: dict[str, str] = {
    "cinematic": "teal shadows, warm highlights, contrast, slight vignette",
    "teal_orange": "blockbuster split-tone",
    "vintage": "faded film, warm, grain, vignette",
    "noir": "black and white, hard contrast, grain",
    "cyberpunk": "neon magenta/cyan, high saturation, bloom",
    "warm": "golden light",
    "cool": "blue hour",
    "bloom": "soft glow on highlights",
    "grain": "film grain only",
    "vignette": "darkened corners only",
    "duotone": "two-colour print look",
    "tilt_shift": "miniature/diorama blur band",
    "hdr": "local contrast (unsharp mask) — not fake HDR brackets",
    "soft_focus": "glamour soft light",
    "cross_process": "wrong-lab colour, punchy",
    "bw_high": "clean high-contrast black and white",
}

IMAGE_TEMPLATES: dict[str, dict] = {
    "instagram_post": {"size": (1080, 1080), "note": "square feed post with title band"},
    "instagram_story": {"size": (1080, 1920), "note": "story/reel cover, safe margins"},
    "youtube_thumb": {"size": (1280, 720), "note": "thumbnail, big bold title"},
    "quote_card": {"size": (1080, 1080), "note": "text-first card, optional photo behind"},
    "product_card": {"size": (1080, 1350), "note": "photo + price band"},
    "passport_photo": {"size": (413, 531), "note": "35×45 mm at 300 dpi, white background"},
    "polaroid": {"size": (900, 1080), "note": "framed print with a caption strip"},
    "link_preview": {"size": (1200, 630), "note": "open-graph card for a website"},
}

STILL_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MAX_CLIPS = 24


# ------------------------------------------------------------------- plumbing
def _ff() -> str:
    return editing._ffmpeg()


def _run(cmd: list[str], timeout: float = 900) -> tuple[bool, str]:
    return editing._run(cmd, timeout=timeout)


def studio_dir() -> Path:
    from . import config
    folder = config.data_dir() / "studio"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _unique(path: Path) -> Path:
    """Two renders inside the same second must not overwrite each other."""
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem}_{int(time.time() * 1000)}{path.suffix}")


def _target(name: str, ext: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "arc")).strip("_")[:48] or "arc"
    return _unique(studio_dir() / f"{safe}_{stamp}{ext}")


def probe(path: str) -> dict:
    """Duration and dimensions, from ffprobe. Empty dict if unreadable."""
    try:
        exe = shutil.which("ffprobe") or "ffprobe"
        out = quiet.run(
            [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
             str(path)], capture_output=True, text=True, timeout=30, errors="replace")
        if out.returncode != 0:
            return {}
        data = json.loads(out.stdout or "{}")
        streams = data.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        return {
            "seconds": float(data.get("format", {}).get("duration") or 0.0),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": video.get("avg_frame_rate") or video.get("r_frame_rate") or "",
            "has_video": bool(video),
            "has_audio": bool(audio),
            "codec": video.get("codec_name") or audio.get("codec_name") or "",
        }
    except Exception:
        return {}


def _split(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    text = str(value or "")
    return [p.strip().strip('"') for p in re.split(r"[|,;]", text) if p.strip()]


def _fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def _textfile(text: str, folder: Path, name: str) -> Path:
    """drawtext with `textfile=` — no escaping hell for colons, quotes or ₹."""
    path = folder / f".{name}.txt"
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------- video
def catalog(kind: str = "all") -> str:
    """Print what exists, so nothing is guessed."""
    kind = (kind or "all").lower()
    lines: list[str] = []
    if kind in ("all", "video", "templates"):
        lines.append(f"VIDEO TEMPLATES ({len(VIDEO_TEMPLATES)})")
        for name, spec in VIDEO_TEMPLATES.items():
            lines.append(f"  {name:18} {spec['aspect']:5} {spec['look']:12} "
                         f"{spec['seconds']:>4}s  {spec['note']}")
        lines.append(f"\nTRANSITIONS ({len(TRANSITIONS)}): " + ", ".join(TRANSITIONS))
        lines.append(f"\nVIDEO LOOKS ({len(VIDEO_LOOKS)}): " + ", ".join(VIDEO_LOOKS))
        lines.append("\nASPECTS: " + ", ".join(f"{k} ({w}×{h})"
                                                for k, (w, h) in ASPECTS.items()))
    if kind in ("all", "audio"):
        lines.append(f"\nAUDIO OPS ({len(AUDIO_OPS)})")
        for name, note in AUDIO_OPS.items():
            lines.append(f"  {name:14} {note}")
    if kind in ("all", "image", "images"):
        lines.append(f"\nIMAGE LOOKS ({len(IMAGE_LOOKS)})")
        for name, note in IMAGE_LOOKS.items():
            lines.append(f"  {name:14} {note}")
        lines.append(f"\nIMAGE TEMPLATES ({len(IMAGE_TEMPLATES)})")
        for name, spec in IMAGE_TEMPLATES.items():
            w, h = spec["size"]
            lines.append(f"  {name:18} {w}×{h:<5} {spec['note']}")
    return "\n".join(lines)


def _look_chain(name: str) -> str:
    chain = VIDEO_LOOKS.get((name or "none").lower())
    if chain is None:
        raise ValueError(f"unknown look '{name}'. Try: {', '.join(VIDEO_LOOKS)}")
    return chain


def video_timeline(clips="", template: str = "reel_hook", transition: str = "",
                   look: str = "", music: str = "", title: str = "",
                   subtitle: str = "", seconds: float = 0.0, duck: bool = True,
                   fade_out: bool = True, fps: int = 30,
                   still_seconds: float = 3.0) -> str:
    """Join clips with real transitions, a look, a caption and an optional music bed.

    Every clip is scaled and padded to the template's aspect, so mixed phone footage
    and screen recordings cut together without black bars jumping around.
    """
    paths = [os.path.expanduser(p) for p in _split(clips)]
    if not paths:
        return ("ERROR: which clips? Give paths separated by '|'. "
                f"Templates: {', '.join(VIDEO_TEMPLATES)}")
    if len(paths) > MAX_CLIPS:
        return f"ERROR: {len(paths)} clips is too many at once (max {MAX_CLIPS})"
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        return f"ERROR: no such file: {missing[0]}"
    spec = VIDEO_TEMPLATES.get((template or "reel_hook").lower())
    if spec is None:
        return (f"ERROR: unknown template '{template}'. Available: "
                f"{', '.join(VIDEO_TEMPLATES)}")
    tr_name = (transition or spec["transition"]).lower()
    if tr_name not in TRANSITIONS:
        return f"ERROR: unknown transition '{transition}'. Available: {', '.join(TRANSITIONS)}"
    look_name = (look or spec["look"]).lower()
    try:
        look_chain = _look_chain(look_name)
    except ValueError as exc:
        return f"ERROR: {exc}"
    if music and not Path(os.path.expanduser(music)).exists():
        return (f"ERROR: no music file at {music}. I will not synthesise a track — "
                f"drop an mp3/wav there or leave music empty.")
    try:
        exe = _ff()
    except RuntimeError as exc:
        return f"ERROR: {exc}"

    width, height = ASPECTS[spec["aspect"]]
    stills = [Path(p).suffix.lower() in STILL_EXT for p in paths]
    infos = [probe(p) for p in paths]
    durations = []
    for path, info, is_still in zip(paths, infos, stills):
        d = float(still_seconds) if is_still else float(info.get("seconds") or 0.0)
        if d <= 0:
            return f"ERROR: could not read a duration from {Path(path).name}"
        durations.append(max(0.5, d))

    xfade = TRANSITIONS[tr_name]
    tdur = 0.6 if xfade else 0.0
    if len(paths) > 1 and xfade and min(durations) <= tdur * 1.6:
        tdur = max(0.12, min(durations) / 4)      # never eat a whole clip
    total = sum(durations) - tdur * (len(paths) - 1)

    filters: list[str] = []
    for i, (path, d, info, is_still) in enumerate(zip(paths, durations, infos, stills)):
        if is_still:
            # a still gets a slow ken-burns push, so a slideshow is not a slideshow
            filters.append(
                f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,fps={fps},"
                f"zoompan=z='min(1.0+0.0012*on,1.10)':d=1:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
                f"trim=0:{d:.3f},setpts=PTS-STARTPTS,fps={fps},settb=AVTB,"
                f"format=yuv420p[v{i}]")
        else:
            filters.append(
                f"[{i}:v]trim=0:{d:.3f},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,fps={fps},settb=AVTB,format=yuv420p[v{i}]")
        if info.get("has_audio"):
            filters.append(f"[{i}:a]atrim=0:{d:.3f},asetpts=PTS-STARTPTS,"
                           f"aresample=48000:async=1[a{i}]")
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{d:.3f},"
                           f"asetpts=PTS-STARTPTS[a{i}]")

    # ---- video chain
    label = "v0"
    offset = 0.0
    for i in range(1, len(paths)):
        offset += durations[i - 1] - tdur
        filters.append(f"[{label}][v{i}]xfade=transition={xfade}:duration={tdur:.3f}:"
                       f"offset={max(0.0, offset):.3f}[vx{i}]")
        label = f"vx{i}"
    if look_chain:
        filters.append(f"[{label}]{look_chain}[vlook]")
        label = "vlook"

    # ---- captions (textfile = no escaping bugs)
    folder = studio_dir()
    if title or subtitle:
        font = _font_path(bold=True)
        esc_font = font.replace(":", r"\:")
        if title:
            tf = _textfile(title, folder, "title")
            filters.append(
                f"[{label}]drawtext=fontfile='{esc_font}':textfile='{tf}':"
                f"fontcolor=white:fontsize={max(18, height // 14)}:borderw=4:"
                f"bordercolor=black@0.7:x=(w-tw)/2:y=h*0.10[vtitle]")
            label = "vtitle"
        if subtitle:
            tf = _textfile(subtitle, folder, "sub")
            filters.append(
                f"[{label}]drawtext=fontfile='{esc_font}':textfile='{tf}':"
                f"fontcolor=white@0.92:fontsize={max(14, height // 26)}:borderw=3:"
                f"bordercolor=black@0.7:x=(w-tw)/2:y=h*0.10+{max(24, height // 13)}"
                f"[vsub]")
            label = "vsub"

    # ---- audio chain
    alabel = "a0"
    for i in range(1, len(paths)):
        filters.append(f"[{alabel}][a{i}]acrossfade=d={tdur:.3f}[ax{i}]")
        alabel = f"ax{i}"

    inputs: list[str] = []
    for path, d, is_still in zip(paths, durations, stills):
        inputs += (["-loop", "1", "-framerate", str(fps), "-t", f"{d:.3f}", "-i", path]
                   if is_still
                   else ["-i", path])
    if music:
        inputs += ["-stream_loop", "-1", "-i", os.path.expanduser(music)]
        mi = len(paths)
        if duck:
            filters.append(f"[{alabel}]asplit=2[voice][sc]")
            filters.append(f"[{mi}:a]volume=0.55,aformat=sample_rates=48000:"
                           f"channel_layouts=stereo[bed]")
            filters.append("[bed][sc]sidechaincompress=threshold=0.03:ratio=8:"
                           "attack=15:release=400[bedduck]")
            filters.append("[voice][bedduck]amix=inputs=2:duration=first:"
                           "dropout_transition=0:normalize=0[amix1]")
        else:
            filters.append(f"[{mi}:a]volume=0.35,aformat=sample_rates=48000:"
                           f"channel_layouts=stereo[bed]")
            filters.append(f"[{alabel}][bed]amix=inputs=2:duration=first[amix1]")
        alabel = "amix1"
    if fade_out:
        filters.append(f"[{alabel}]afade=t=in:st=0:d=0.35,"
                       f"afade=t=out:st={max(0.0, total - 0.8):.2f}:d=0.8[afade]")
        alabel = "afade"
    if total >= 3.0:
        filters.append(f"[{alabel}]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    else:
        # loudnorm needs a few seconds of audio to measure; below that it errors out
        filters.append(f"[{alabel}]alimiter=limit=0.95[aout]")

    out = _target(f"{template}", ".mp4")
    cmd = [exe, "-y", "-v", "error", *inputs,
           "-filter_complex", ";".join(filters),
           "-map", f"[{label}]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-threads", "2", "-movflags", "+faststart"]
    if seconds and float(seconds) > 0:
        cmd += ["-t", f"{float(seconds):.3f}"]
    cmd.append(str(out))
    ok, err = _run(cmd)
    if not ok:
        return f"ERROR: ffmpeg failed — {err}"
    size = out.stat().st_size / 1e6
    return (f"{template} built → {out} ({size:.1f} MB, {_fmt_time(total)} of video)\n"
            f"  {len(paths)} clip(s){' (with ken-burns on stills)' if any(stills) else ''}"
            f" · transition {tr_name} ({tdur:.2f}s) · "
            f"look {look_name} · {width}×{height} · {fps} fps\n"
            f"  {'music: ' + Path(music).name + (' (ducked under the voice)' if duck else '') if music else 'music: none (add one with music=...)'}\n"
            "  originals untouched.")


def video_look(path: str = "", look: str = "cinematic", strength: float = 1.0,
               out: str = "") -> str:
    """Grade one clip. `strength` < 1 mixes the original back in."""
    src = Path(os.path.expanduser(str(path or "")))
    if not src.exists():
        return f"ERROR: no such video: {src}"
    try:
        chain = _look_chain(look)
        exe = _ff()
    except (ValueError, RuntimeError) as exc:
        return f"ERROR: {exc}"
    target = (Path(os.path.expanduser(out)) if out
              else _unique(editing._out(str(src), f"look_{look}")))
    if not chain:
        return "ERROR: 'none' is not a look — pick one: " + ", ".join(VIDEO_LOOKS)
    amount = max(0.0, min(1.0, float(strength)))
    if amount >= 0.999:
        final = chain
    else:
        final = (f"split[orig][grad];[grad]{chain}[l];"
                 f"[orig][l]blend=all_mode=normal:all_opacity={amount:.2f}")
    ok, err = _run([exe, "-y", "-v", "error", "-i", str(src), "-filter_complex", final,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "copy", str(target)])
    if not ok:
        return f"ERROR: ffmpeg failed — {err}"
    info = probe(str(target))
    return (f"{look} at {int(amount * 100)}% → {target.name} "
            f"({target.stat().st_size / 1e6:.1f} MB, {_fmt_time(info.get('seconds', 0))}). "
            f"Original untouched.")


def video_gif(path: str = "", start: float = 0.0, seconds: float = 4.0,
              width: int = 540) -> str:
    return editing.edit_video(path, "gif", start=start, seconds=seconds, width=width)


# --------------------------------------------------------------------- audio
def _atempo(factor: float) -> str:
    """atempo only accepts 0.5–2.0 per instance, so chain instances."""
    parts = []
    f = max(0.25, min(4.0, float(factor)))
    while f > 2.0:
        parts.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5")
        f /= 0.5
    parts.append(f"atempo={f:.4f}")
    return ",".join(parts)


def audio_op(path: str = "", op: str = "denoise", target_lufs: float = -14.0,
             bass: float = 0.0, mid: float = 0.0, treble: float = 0.0,
             start: float = 0.0, end: float = 0.0, factor: float = 1.0,
             seconds: float = 1.0, db: float = 3.0, as_format: str = "") -> str:
    """One audio operation, one new file. Every filter is ffmpeg's, measured output."""
    src = Path(os.path.expanduser(str(path or "")))
    if not src.exists():
        return f"ERROR: no such audio: {src}"
    op = (op or "").strip().lower()
    if op not in AUDIO_OPS:
        return f"ERROR: unknown audio op '{op}'. Available: {', '.join(AUDIO_OPS)}"
    try:
        exe = _ff()
    except RuntimeError as exc:
        return f"ERROR: {exc}"
    if op == "chapters":
        return audio_chapters(str(src))

    ext = f".{as_format.lstrip('.')}" if as_format else src.suffix
    target = _unique(editing._out(str(src), op, ext=ext))
    chain = {
        "denoise": "highpass=f=80,afftdn=nf=-25",
        "deess": "deesser=i=0.6",
        "gate": "agate=threshold=0.02:ratio=4:attack=5:release=200",
        "compress": "acompressor=threshold=-18dB:ratio=4:attack=8:release=200",
        "eq3": (f"equalizer=f=120:t=q:w=1:g={float(bass):.1f},"
                f"equalizer=f=1000:t=q:w=1:g={float(mid):.1f},"
                f"equalizer=f=6000:t=q:w=1:g={float(treble):.1f}"),
        "reverb": "aecho=0.8:0.85:40|70:0.28|0.18",
        "loudnorm": f"loudnorm=I={float(target_lufs):.1f}:TP=-1.5:LRA=11",
        "fade": (f"afade=t=in:st=0:d={max(0.1, float(seconds))},"
                 f"areverse,afade=t=in:st=0:d={max(0.1, float(seconds))},areverse"),
        "speed": _atempo(factor),
        "mono": "", "stereo_width": "extrastereo=m=1.8",
        "silence_trim": ("silenceremove=start_periods=1:start_threshold=-45dB:"
                         "detection=peak:stop_periods=-1:stop_threshold=-45dB"),
    }.get(op, "")
    cmd = [exe, "-y", "-v", "error"]
    if op == "trim":
        cmd += ["-ss", str(max(0.0, float(start)))]
        if end:
            cmd += ["-to", str(float(end))]
        cmd += ["-i", str(src), "-c", "copy"]
    else:
        cmd += ["-i", str(src)]
        if chain:
            cmd += ["-af", chain]
        if op == "mono":
            cmd += ["-ac", "1"]
    cmd.append(str(target))
    ok, err = _run(cmd)
    if not ok:
        return f"ERROR: ffmpeg failed — {err}"
    info = probe(str(target))
    return (f"{op} → {target.name} ({_fmt_time(info.get('seconds', 0))}, "
            f"{target.stat().st_size / 1024:.0f} KB). Original untouched.")


def audio_mix(tracks="", gains="", out_name: str = "mix", target_lufs: float = -14.0,
              duck: bool = False) -> str:
    """Mix several tracks. `gains` = dB per track, e.g. "-6,-18" (voice, music)."""
    paths = [os.path.expanduser(p) for p in _split(tracks)]
    if len(paths) < 2:
        return "ERROR: mixing needs at least two files (path|path)"
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        return f"ERROR: no such file: {missing[0]}"
    try:
        exe = _ff()
    except RuntimeError as exc:
        return f"ERROR: {exc}"
    levels = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(gains or ""))]
    levels += [0.0] * (len(paths) - len(levels))
    filters, labels = [], []
    for i, path in enumerate(paths):
        filters.append(f"[{i}:a]volume={levels[i]:.1f}dB,aformat=sample_rates=48000:"
                       f"channel_layouts=stereo[a{i}]")
        labels.append(f"[a{i}]")
    if duck and len(paths) == 2:
        filters.append("[a0]asplit=2[voice][sc]")
        filters.append("[a1][sc]sidechaincompress=threshold=0.03:ratio=8:attack=15:"
                       "release=400[bedduck]")
        filters.append("[voice][bedduck]amix=inputs=2:duration=first[amixraw]")
    else:
        filters.append(f"{''.join(labels)}amix=inputs={len(paths)}:duration=longest:"
                       f"dropout_transition=0[amixraw]")
    filters.append(f"[amixraw]loudnorm=I={float(target_lufs):.1f}:TP=-1.5:LRA=11[aout]")
    out = _target(out_name, ".wav")
    cmd = [exe, "-y", "-v", "error"]
    for path in paths:
        cmd += ["-i", path]
    cmd += ["-filter_complex", ";".join(filters), "-map", "[aout]", str(out)]
    ok, err = _run(cmd)
    if not ok:
        return f"ERROR: ffmpeg failed — {err}"
    info = probe(str(out))
    return (f"mix → {out.name} ({_fmt_time(info.get('seconds', 0))}, "
            f"{len(paths)} tracks, levels {', '.join(f'{x:+.1f}dB' for x in levels)}"
            f"{', music ducked under the voice' if duck else ''})")


def audio_chapters(path: str = "") -> str:
    """Where the speech starts and stops, from silence detection — no guessing."""
    src = Path(os.path.expanduser(str(path or "")))
    if not src.exists():
        return f"ERROR: no such audio: {src}"
    try:
        exe = _ff()
    except RuntimeError as exc:
        return f"ERROR: {exc}"
    proc = quiet.run([exe, "-v", "info", "-i", str(src), "-af",
                           "silencedetect=noise=-38dB:d=0.45", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=300, errors="replace")
    stamps = re.findall(r"silence_(start|end): ([\d.]+)", proc.stderr or "")
    if not stamps:
        return ("No silences found at -38 dB / 0.45 s — either it is continuous sound or "
                "very quiet. Nothing invented; try a different threshold.")
    lines, index = [], 0
    for kind, value in stamps:
        if kind == "end":
            index += 1
            lines.append(f"  {index:02d}. speech starts {_fmt_time(float(value))}")
    info = probe(str(src))
    head = (f"{Path(src).name} — {_fmt_time(info.get('seconds', 0))}, "
            f"{len(lines)} speech block(s)")
    return head + "\n" + "\n".join(lines[:60])


def audio_waveform(path: str = "", width: int = 1200, height: int = 300,
                   colour: str = "#48f2ff") -> str:
    src = Path(os.path.expanduser(str(path or "")))
    if not src.exists():
        return f"ERROR: no such audio: {src}"
    try:
        exe = _ff()
    except RuntimeError as exc:
        return f"ERROR: {exc}"
    out = _target(f"{src.stem}_wave", ".png")
    ok, err = _run([exe, "-y", "-v", "error", "-i", str(src), "-filter_complex",
                    f"showwavespic=s={int(width)}x{int(height)}:colors={colour}",
                    "-frames:v", "1", str(out)])
    return (f"waveform → {out}" if ok else f"ERROR: ffmpeg failed — {err}")


# --------------------------------------------------------------------- images
def _font_path(bold: bool = True) -> str:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return ""


def _font(size: int, bold: bool = True):
    from PIL import ImageFont
    path = _font_path(bold)
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default(size)


def _cover(img, width: int, height: int):
    """Scale-and-crop to fill, like CSS object-fit: cover."""
    from PIL import Image
    scale = max(width / img.width, height / img.height)
    resized = img.resize((max(1, int(img.width * scale + 0.5)),
                          max(1, int(img.height * scale + 0.5))), Image.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _vignette(img, strength: float = 0.55):
    """Darken the corners. radial_gradient is 0 in the middle and 255 at the corners."""
    from PIL import Image
    img = img.convert("RGB")
    mask = Image.radial_gradient("L").resize(img.size, Image.BILINEAR)
    # quadratic falloff: the middle of the frame stays clean, only the corners go dark
    mask = mask.point(lambda v: int(min(255, 255 * (v / 255.0) ** 2 * strength)))
    dark = Image.new("RGB", img.size, (0, 0, 0))
    return Image.composite(dark, img, mask)


def _grain(img, amount: float = 12.0):
    from PIL import Image, ImageChops
    noise = Image.effect_noise(img.size, amount).convert("L")
    tinted = Image.merge("RGB", (noise, noise, noise))
    return ImageChops.blend(img.convert("RGB"), ImageChops.add(img.convert("RGB"), tinted,
                                                              scale=2.0, offset=-40), 0.35)


def _tone_curve(img, shadow_rgb, highlight_rgb, strength: float = 0.35):
    """Split-tone: push shadows one way and highlights another (channel-wise)."""
    from PIL import Image
    bands = img.convert("RGB").split()
    out = []
    for channel, (lo, hi) in zip(bands, zip(shadow_rgb, highlight_rgb)):
        lut = []
        for v in range(256):
            t = v / 255.0
            weight = (1 - t) * lo + t * hi
            lut.append(max(0, min(255, int(v + weight * 255 * strength))))
        out.append(channel.point(lut))
    return Image.merge("RGB", out)


def _bloom(img, radius: float = 12.0, strength: float = 0.4):
    from PIL import ImageChops, ImageFilter
    blurred = img.filter(ImageFilter.GaussianBlur(radius))
    return ImageChops.blend(img, ImageChops.screen(img, blurred), strength)


def _tilt_shift(img, band: float = 0.38):
    from PIL import Image, ImageFilter
    blurred = img.filter(ImageFilter.GaussianBlur(max(2.0, img.width / 90)))
    mask = Image.new("L", img.size, 255)
    draw_band = int(img.height * band)
    from PIL import ImageDraw
    ImageDraw.Draw(mask).rectangle(
        (0, (img.height - draw_band) // 2, img.width,
         (img.height + draw_band) // 2), fill=0)
    mask = mask.filter(ImageFilter.GaussianBlur(img.height / 18))
    return Image.composite(img, blurred, mask)


def image_look(path: str = "", look: str = "cinematic", strength: float = 1.0,
               out: str = "", colour2: str = "#f4d06f") -> str:
    """Apply a look with Pillow (no shaders, no GPU). `strength` 0–1."""
    try:
        from PIL import ImageEnhance, ImageFilter, ImageOps
    except Exception:
        return "ERROR: pillow is not installed (pip install pillow)"
    src = Path(os.path.expanduser(str(path or "")))
    if not src.exists():
        return f"ERROR: no such image: {src}"
    key = (look or "cinematic").strip().lower()
    if key not in IMAGE_LOOKS:
        return f"ERROR: unknown look '{look}'. Available: {', '.join(IMAGE_LOOKS)}"
    amount = max(0.0, min(1.0, float(strength)))
    try:
        img = ImageOps.exif_transpose(_open_rgb(src))
    except Exception as exc:
        return f"ERROR: could not read {src.name} ({type(exc).__name__})"

    def graded():
        im = img
        if key in ("cinematic", "teal_orange"):
            im = _tone_curve(im, (-0.05, 0.0, 0.10), (0.06, 0.0, -0.05), 0.9)
            im = ImageEnhance.Contrast(im).enhance(1.10)
            im = ImageEnhance.Color(im).enhance(1.08)
            im = _vignette(im, 0.22 if key == "cinematic" else 0.12)
        elif key == "vintage":
            im = ImageOps.colorize(ImageOps.grayscale(im),
                                   black="#2b2118", white="#f6e7c8")
            im = ImageEnhance.Contrast(im).enhance(0.92)
            im = _grain(im, 10)
            im = _vignette(im, 0.35)
        elif key == "noir":
            im = ImageOps.grayscale(im).convert("RGB")
            im = ImageEnhance.Contrast(im).enhance(1.35)
            im = _grain(im, 9)
            im = _vignette(im, 0.3)
        elif key == "bw_high":
            im = ImageEnhance.Contrast(ImageOps.grayscale(im).convert("RGB")).enhance(1.6)
        elif key == "cyberpunk":
            im = _tone_curve(im, (0.10, -0.06, 0.16), (0.10, 0.0, 0.12), 0.9)
            im = ImageEnhance.Color(im).enhance(1.45)
            im = _bloom(im, img.width / 90, 0.45)
            im = ImageEnhance.Contrast(im).enhance(1.08)
        elif key == "warm":
            im = _tone_curve(im, (0.03, 0.01, -0.03), (0.09, 0.02, -0.08), 0.85)
        elif key == "cool":
            im = _tone_curve(im, (-0.03, 0.0, 0.07), (-0.08, 0.0, 0.10), 0.85)
        elif key == "bloom":
            im = _bloom(im, img.width / 70, 0.5)
        elif key == "grain":
            im = _grain(im, 14)
        elif key == "vignette":
            im = _vignette(im, 0.55)
        elif key == "duotone":
            im = ImageOps.colorize(ImageOps.grayscale(im), black="#04121a",
                                   white=colour2)
        elif key == "tilt_shift":
            im = _tilt_shift(im)
        elif key == "hdr":
            im = im.filter(ImageFilter.UnsharpMask(radius=18, percent=120, threshold=2))
            im = ImageEnhance.Contrast(im).enhance(1.12)
        elif key == "soft_focus":
            glow = im.filter(ImageFilter.GaussianBlur(img.width / 120))
            from PIL import ImageChops
            im = ImageChops.screen(im, ImageChops.blend(im, glow, 0.55))
        elif key == "cross_process":
            im = _tone_curve(im, (-0.06, 0.06, 0.14), (0.14, -0.02, -0.12), 1.0)
            im = ImageEnhance.Contrast(im).enhance(1.2)
        return im

    graded_img = graded()
    if amount < 0.999:
        from PIL import ImageChops
        graded_img = ImageChops.blend(img, graded_img, amount)
    target = (Path(os.path.expanduser(out)) if out
              else _unique(editing._out(str(src), f"look_{key}", ext=".png")))
    graded_img.save(target, quality=95)
    return (f"{key} at {int(amount * 100)}% → {target.name} "
            f"({graded_img.width}×{graded_img.height}, "
            f"{target.stat().st_size / 1024:.0f} KB). Original untouched.")


def _open_rgb(src: Path):
    from PIL import Image
    img = Image.open(src)
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        base = Image.new("RGB", img.size, (12, 14, 16))
        rgba = img.convert("RGBA")
        base.paste(rgba, (0, 0), rgba)
        return base
    return img.convert("RGB")


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words, lines, current = str(text).split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:8]


def image_card(path: str = "", template: str = "instagram_post", title: str = "",
               subtitle: str = "", look: str = "", footer: str = "",
               background: str = "#0b1213", accent: str = "#48f2ff") -> str:
    """A finished card: photo (optional) + gradient scrim + title + subtitle."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return "ERROR: pillow is not installed (pip install pillow)"
    key = (template or "instagram_post").strip().lower()
    spec = IMAGE_TEMPLATES.get(key)
    if spec is None:
        return (f"ERROR: unknown template '{template}'. Available: "
                f"{', '.join(IMAGE_TEMPLATES)}")
    width, height = spec["size"]
    background = background or "#0b1213"
    accent = accent or "#48f2ff"
    photo = None
    if path:
        src = Path(os.path.expanduser(str(path)))
        if not src.exists():
            return f"ERROR: no such image: {src}"
        try:
            photo = _open_rgb(src)
            if look:
                tmp = _target("look_tmp", ".png")
                graded = image_look(str(src), look, 1.0, out=str(tmp))
                if graded.startswith("ERROR"):
                    return graded
                photo = _open_rgb(tmp)
        except Exception as exc:
            return f"ERROR: could not read {src.name} ({type(exc).__name__})"
    try:
        if key == "polaroid":
            canvas = Image.new("RGB", (width, height), "#f7f4ec")
            if photo is not None:
                canvas.paste(_cover(photo, width - 90, height - 240), (45, 45))
        elif photo is not None:
            canvas = _cover(photo, width, height)
        else:
            canvas = Image.new("RGB", (width, height), background)
    except Exception as exc:
        return f"ERROR: could not build {key} ({type(exc).__name__}: {exc})"
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = int(width * 0.07)
    bottom_pad = int(height * (0.07 if key not in ("passport_photo",) else 0.05))
    title_size = int(height * (0.075 if key != "youtube_thumb" else 0.105))
    sub_size = int(height * 0.032)
    title_font = _font(title_size, bold=True)
    sub_font = _font(sub_size, bold=False)
    title_lines = _wrap(draw, title, title_font, width - margin * 2) if title else []
    sub_lines = _wrap(draw, subtitle, sub_font, width - margin * 2) if subtitle else []

    # lay the text out from the bottom up so a two-line title can never collide
    sub_block = int(sub_size * 1.34) * len(sub_lines)
    title_block = int(title_size * 1.22) * len(title_lines)
    gap = int(height * 0.018) if (title_lines and sub_lines) else 0
    if sub_lines:
        y = height - bottom_pad - sub_block
        for line in sub_lines:
            draw.text((margin, y), line, font=sub_font, fill=(255, 255, 255, 205))
            y += int(sub_size * 1.34)
    if title_lines:
        y = height - bottom_pad - sub_block - gap - title_block
        for line in title_lines:
            draw.text((margin, y), line, font=title_font, fill=(255, 255, 255, 248))
            y += int(title_size * 1.22)

    # scrim behind the text, so it reads over any photo
    if (title_lines or sub_lines) and key != "passport_photo":
        top = height - bottom_pad - sub_block - gap - title_block - int(height * 0.06)
        top = max(0, top)
        for i in range(height - top):
            alpha = int(215 * (i / max(1, height - top)) ** 1.5)
            draw.rectangle([0, top + i, width, top + i + 1], fill=(6, 10, 12, alpha))
        if title_lines:
            y = height - bottom_pad - sub_block - gap - title_block
            for line in title_lines:
                draw.text((margin, y), line, font=title_font, fill=(255, 255, 255, 248))
                y += int(title_size * 1.22)
        if sub_lines:
            y = height - bottom_pad - sub_block
            for line in sub_lines:
                draw.text((margin, y), line, font=sub_font, fill=(255, 255, 255, 210))
                y += int(sub_size * 1.34)

    if footer:
        size = max(16, int(height * 0.028))
        font = _font(size, bold=True)
        draw.text((margin, margin), footer, font=font, fill=accent)
        bar_w = int(max(40, draw.textlength(footer, font=font) + 18))
        draw.rectangle([margin - 8, margin - 5, margin - 8 + bar_w, margin + size + 7],
                       outline=accent, width=2)
    if key == "polaroid" and footer:
        draw.text((45, height - 150), footer, font=_font(int(height * 0.05), True),
                  fill="#20201c")

    target = _target(key, ".jpg")
    canvas.save(target, quality=92, optimize=True)
    note = "photo" if path else "generated background"
    return (f"{key} → {target} ({width}×{height}, {note}, "
            f"{target.stat().st_size / 1024:.0f} KB)")


def _upright(src: Path):
    """Honour the phone's EXIF rotation before anything else touches the pixels."""
    from PIL import ImageOps
    return ImageOps.exif_transpose(_open_rgb(src))


def image_collage(images="", cols: int = 2, rows: int = 2, cell: int = 640,
                  gap: int = 12, background: str = "#0b1213",
                  title: str = "", look: str = "") -> str:
    """Grid collage from N images; missing cells stay background (no repeats)."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return "ERROR: pillow is not installed (pip install pillow)"
    paths = [Path(os.path.expanduser(p)) for p in _split(images)]
    if not paths:
        return "ERROR: which images? Give paths separated by '|'"
    missing = [p for p in paths if not p.exists()]
    if missing:
        return f"ERROR: no such image: {missing[0]}"
    cols = max(1, min(6, int(cols)))
    rows = max(1, min(6, int(rows)))
    capacity = cols * rows
    if len(paths) > capacity:
        paths = paths[:capacity]
    cell = max(120, int(cell))
    top = int(cell * 0.18) if title else 0
    width, height = cols * cell + gap * (cols + 1), rows * cell + gap * (rows + 1) + top
    canvas = Image.new("RGB", (width, height), background)
    for index, path in enumerate(paths):
        row, col = divmod(index, cols)
        x = gap + col * (cell + gap)
        y = top + gap + row * (cell + gap)
        tile = _cover(_upright(path), cell, cell)
        if look:
            tmp = _target("tile", ".png")
            tile.save(tmp)
            if image_look(str(tmp), look, 1.0, out=str(tmp)).startswith("ERROR"):
                return f"ERROR: look '{look}' failed"
            tile = _open_rgb(tmp)
        canvas.paste(tile, (x, y))
    if title:
        draw = ImageDraw.Draw(canvas)
        draw.text((gap + 4, int(top * 0.30)), title,
                  font=_font(int(top * 0.62), True), fill="#e8f7ff")
    target = _target("collage", ".jpg")
    canvas.save(target, quality=90, optimize=True)
    return (f"collage {cols}×{rows} → {target} ({len(paths)} image(s), "
            f"{width}×{height}, {target.stat().st_size / 1024:.0f} KB)")


def image_batch(folder: str = "", look: str = "cinematic", strength: float = 0.85,
                limit: int = 40) -> str:
    """Apply a look to every image in a folder — new files, originals untouched."""
    root = Path(os.path.expanduser(str(folder or "")))
    if not root.is_dir():
        return f"ERROR: not a folder: {root}"
    if (look or "").lower() not in IMAGE_LOOKS:
        return f"ERROR: unknown look '{look}'. Available: {', '.join(IMAGE_LOOKS)}"
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    files = [p for p in sorted(root.iterdir()) if p.suffix.lower() in exts][:int(limit)]
    if not files:
        return f"ERROR: no images in {root}"
    done, failed = [], []
    for path in files:
        out = _unique(editing._out(str(path), f"look_{look}", ext=".png"))
        result = image_look(str(path), look, strength, out=str(out))
        (done if not result.startswith("ERROR") else failed).append(path.name)
    return (f"{len(done)} image(s) graded with {look} in {root}"
            + (f"; {len(failed)} failed ({', '.join(failed[:3])})" if failed else "")
            + f". New files are siblings named *_look_{look}_*.png — originals untouched.")


# ---------------------------------------------------------------- one entry
def run(kind: str = "catalog", action: str = "", path: str = "", **kw) -> str:
    """Single dispatch used by the tool layer and the Lite intents."""
    key = (kind or "catalog").strip().lower()
    act = (action or "").strip().lower()
    if key in ("catalog", "list", "templates"):
        return catalog(act or "all")
    if key == "video":
        if act in ("template", "timeline", "make", "build", "reel", ""):
            return video_timeline(
                clips=kw.get("clips") or kw.get("images") or path,
                template=kw.get("template") or "reel_hook",
                transition=kw.get("transition") or "",
                look=kw.get("look") or "",
                music=kw.get("music") or "",
                title=kw.get("title") or "",
                subtitle=kw.get("subtitle") or "",
                seconds=float(kw.get("seconds") or 0),
                duck=kw.get("duck", True) if isinstance(kw.get("duck"), bool) else True,
                fps=int(kw.get("fps") or 30))
        if act in ("look", "grade", "effect", "filter"):
            return video_look(path or (kw.get("clips") or ""),
                              kw.get("look") or "cinematic",
                              float(kw.get("strength") or 1.0))
        if act == "gif":
            return video_gif(path, float(kw.get("start") or 0),
                             float(kw.get("seconds") or 4),
                             int(kw.get("width") or 540))
        return (f"ERROR: unknown video action '{action}'. "
                f"Use template | look | gif | catalog.")
    if key == "audio":
        if act in ("mix", "mixdown"):
            return audio_mix(kw.get("clips") or path, kw.get("gains") or "",
                             kw.get("title") or "mix",
                             float(kw.get("target_lufs") or -14),
                             bool(kw.get("duck")))
        if act in ("waveform", "wave"):
            return audio_waveform(path, int(kw.get("width") or 1200),
                                  int(kw.get("height") or 300),
                                  kw.get("colour") or "#48f2ff")
        return audio_op(path, act or kw.get("op") or "denoise",
                        float(kw.get("target_lufs") or -14),
                        float(kw.get("bass") or 0), float(kw.get("mid") or 0),
                        float(kw.get("treble") or 0),
                        float(kw.get("start") or 0), float(kw.get("end") or 0),
                        float(kw.get("factor") or 1.0),
                        float(kw.get("seconds") or 1.0),
                        float(kw.get("db") or 3.0),
                        str(kw.get("as") or ""))
    if key == "image":
        if act in ("look", "grade", "filter", "effect"):
            return image_look(path, kw.get("look") or "cinematic",
                              float(kw.get("strength") or 1.0),
                              kw.get("out") or "")
        if act in ("card", "template", "post", "story", "thumb"):
            return image_card(path, kw.get("template") or act or "instagram_post",
                              kw.get("title") or "", kw.get("subtitle") or "",
                              kw.get("look") or "", kw.get("footer") or "",
                              kw.get("background") or "#0b1213",
                              kw.get("accent") or "#48f2ff")
        if act in ("collage", "grid"):
            return image_collage(kw.get("images") or path,
                                 int(kw.get("cols") or 2), int(kw.get("rows") or 2),
                                 int(kw.get("cell") or 640), int(kw.get("gap") or 12),
                                 kw.get("background") or "#0b1213",
                                 kw.get("title") or "", kw.get("look") or "")
        if act in ("batch", "folder"):
            return image_batch(path, kw.get("look") or "cinematic",
                               float(kw.get("strength") or 0.85))
        return (f"ERROR: unknown image action '{action}'. "
                f"Use look | card | collage | batch | catalog.")
    return (f"ERROR: unknown kind '{kind}'. Use video | audio | image | catalog.")
