#!/usr/bin/env python3
"""Build `arcdesk/STUDIO_PAGE.html` — a gallery of renders that really happened.

Everything on the page is produced by `arcdesk/media.py` during the build: the looks,
the cards, the collage, the waveform, and a rendered reel whose frames are pulled out
of the finished MP4. Nothing is a mock-up, and every size/duration printed is read
back from the file with ffprobe.

    python tools/make_studio_page.py
"""
from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-studio-page-"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk import media  # noqa: E402

OUT = ROOT / "arcdesk" / "STUDIO_PAGE.html"
WORK = Path(tempfile.mkdtemp(prefix="arcdesk-gallery-"))
FF = shutil.which("ffmpeg")
FP = shutil.which("ffprobe")


def jpeg(path: Path, width: int = 720, quality: int = 82) -> str:
    from PIL import Image
    with Image.open(path) as img:
        img = img.convert("RGB")
        if img.width > width:
            img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def make_photo() -> Path:
    """A stand-in photo with skin-ish and sky-ish tones, so grades are visible."""
    from PIL import Image, ImageDraw
    width, height = 1400, 1000
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / height
        r = int(28 + 120 * t ** 0.8)
        g = int(58 + 110 * t ** 1.1)
        b = int(96 + 90 * (1 - t) ** 1.4)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    # sun
    draw.ellipse([980, 120, 1240, 380], fill=(255, 214, 140))
    # hills
    draw.polygon([(0, 760), (420, 520), (820, 780), (1400, 600), (1400, 1000), (0, 1000)],
                 fill=(22, 46, 38))
    draw.polygon([(0, 880), (520, 720), (1000, 900), (1400, 820), (1400, 1000), (0, 1000)],
                 fill=(12, 28, 24))
    # a rooftop table
    draw.rectangle([120, 700, 520, 760], fill=(196, 156, 108))
    draw.rectangle([150, 760, 176, 940], fill=(150, 116, 78))
    draw.ellipse([300, 640, 372, 700], fill=(248, 248, 244))
    return _save(img, "photo.png")


def make_clips() -> tuple[Path, Path]:
    one, two = WORK / "clip_a.mp4", WORK / "clip_b.mp4"
    subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=960x540:rate=30:duration=2.4", "-f", "lavfi", "-i",
                    "sine=frequency=392:duration=2.4", "-c:v", "libx264", "-preset",
                    "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(one)],
                   check=True, timeout=120)
    subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i",
                    "smptebars=size=540x960:rate=30:duration=2.0", "-f", "lavfi", "-i",
                    "sine=frequency=523:duration=2.0", "-c:v", "libx264", "-preset",
                    "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(two)],
                   check=True, timeout=120)
    return one, two


def make_voice() -> Path:
    voice = WORK / "voice.wav"
    subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=220:duration=3", str(voice)], check=True, timeout=120)
    return voice


def frame(mp4: Path, at: float, name: str) -> Path:
    out = WORK / name
    subprocess.run([FF, "-y", "-v", "error", "-ss", f"{at}", "-i", str(mp4),
                    "-frames:v", "1", str(out)], check=True, timeout=120)
    return out


def _save(img, name: str) -> Path:
    path = WORK / name
    img.save(path)
    return path


def short(reply: str) -> str:
    """Same reply, with the throw-away build folder removed for readability."""
    return reply.replace(str(WORK) + os.sep, "").replace(str(WORK), ".")


def path_of(reply: str) -> Path:
    """Every media function returns '... → <path> (...)' — take the path back out."""
    raw = reply.split(" → ")[1].split(" (")[0].strip() if " → " in reply else reply.strip()
    path = Path(raw)
    return path if path.is_absolute() else WORK / path


def build() -> str:
    photo = make_photo()
    clip_a, clip_b = make_clips()
    voice = make_voice()

    looks = [("original", None), ("cinematic", "cinematic"), ("noir", "noir"),
             ("cyberpunk", "cyberpunk")]
    look_tiles = []
    for label, look in looks:
        if look is None:
            look_tiles.append((label, jpeg(photo, 560)))
            continue
        reply = media.image_look(str(photo), look, 1.0,
                                 out=str(WORK / f"look_{look}.png"))
        look_tiles.append((label, jpeg(path_of(reply), 560)))

    cards = []
    for label, template, title, subtitle in (
            ("instagram_post", "instagram_post", "Neeli rooftop cafe",
             "Breakfast included on direct bookings"),
            ("instagram_story", "instagram_story", "Room 12", "season tariff ₹4200"),
            ("youtube_thumb", "youtube_thumb", "Hampi in 3 days", "what nobody tells you")):
        reply = media.image_card(str(photo), template, title, subtitle, footer="ARC DESK")
        cards.append((label, jpeg(path_of(reply), 520), short(reply)))

    collage_reply = media.image_collage(f"{photo}|{photo}|{photo}|{photo}", 2, 2, 420,
                                        title="BELAGAVI")
    collage_img = jpeg(path_of(collage_reply), 620)
    wave_reply = media.audio_waveform(str(voice), 1200, 240)
    wave_img = jpeg(path_of(wave_reply), 900)

    reel_reply = media.video_timeline(f"{clip_a}|{clip_b}", template="story",
                                      transition="fade", look="cinematic",
                                      title="Belagavi sunrise", subtitle="room 12 · rooftop")
    reel = path_of(reel_reply)
    reel_info = media.probe(str(reel))
    reel_frames = [jpeg(frame(reel, at, f"reel_{i}.png"), 380)
                   for i, at in enumerate((0.3, 1.4, 2.5))]

    audio_rows = []
    for op in ("denoise", "loudnorm", "eq3"):
        reply = media.audio_op(str(voice), op)
        audio_rows.append((op, reply))
    loudness = media.audio_op(str(voice), "loudnorm", target_lufs=-16)

    stats = {
        "templates": len(media.VIDEO_TEMPLATES),
        "transitions": len(media.TRANSITIONS),
        "vlooks": len(media.VIDEO_LOOKS),
        "ilooks": len(media.IMAGE_LOOKS),
        "itemplates": len(media.IMAGE_TEMPLATES),
        "audio": len(media.AUDIO_OPS),
        "reel_seconds": reel_info.get("seconds", 0),
        "reel_size": reel.stat().st_size / 1e6,
        "reel_w": reel_info.get("width", 0),
        "reel_h": reel_info.get("height", 0),
    }

    def tile(label: str, src: str, caption: str = "") -> str:
        return f"""
        <figure class="tile">
          <img src="{src}" alt="{label}">
          <figcaption><b>{label}</b>{f'<span>{caption}</span>' if caption else ''}</figcaption>
        </figure>"""

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ARC DESK · studio</title>
<style>
  :root {{ --void:#01050a; --ink:#d8f6ff; --dim:#6f97a6; --cy:#48f2ff;
           --gold:#f4d06f; --line:rgba(72,242,255,.26); }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px 20px 64px; color:var(--ink);
    font:15px/1.6 "Segoe UI",system-ui,sans-serif;
    background:radial-gradient(1200px 700px at 50% -10%, #06222b 0, transparent 62%),
      radial-gradient(900px 520px at 88% 100%, #0a1e26 0, transparent 58%), var(--void); }}
  .wrap {{ max-width:1120px; margin:0 auto; }}
  .frame {{ position:relative; border:1px solid var(--line); padding:26px 24px 30px;
    background:linear-gradient(180deg, rgba(9,32,40,.7), rgba(2,9,14,.88)); }}
  .frame::before,.frame::after {{ content:""; position:absolute; width:22px; height:22px;
    border:2px solid var(--cy); }}
  .frame::before {{ top:-1px; left:-1px; border-right:0; border-bottom:0; }}
  .frame::after {{ bottom:-1px; right:-1px; border-left:0; border-top:0; }}
  h1 {{ margin:0 0 4px; font:600 25px/1.2 "Segoe UI"; letter-spacing:.32em;
    text-transform:uppercase; color:var(--cy); }}
  h1 span {{ color:var(--ink); letter-spacing:.05em; font-weight:300; }}
  .sub {{ color:var(--dim); font-size:13px; margin-bottom:20px; }}
  .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
    gap:9px; margin-bottom:26px; }}
  .stat {{ border:1px solid var(--line); padding:10px 12px; background:rgba(6,26,33,.55); }}
  .stat b {{ display:block; font:600 22px/1.1 Consolas,monospace; color:var(--cy); }}
  .stat i {{ font-style:normal; font-size:10.5px; letter-spacing:.15em; color:var(--dim);
    text-transform:uppercase; }}
  h2 {{ font:500 12.5px/1 "Segoe UI"; letter-spacing:.26em; text-transform:uppercase;
    color:var(--cy); margin:32px 0 12px; padding-bottom:8px; border-bottom:1px solid var(--line); }}
  .grid {{ display:grid; gap:12px; }}
  .g4 {{ grid-template-columns:repeat(auto-fit,minmax(215px,1fr)); }}
  .g3 {{ grid-template-columns:repeat(auto-fit,minmax(255px,1fr)); }}
  .tile {{ margin:0; border:1px solid var(--line); background:rgba(4,17,23,.6); }}
  .tile img {{ display:block; width:100%; height:auto; }}
  figcaption {{ padding:8px 10px; font-size:12.5px; color:var(--ink);
    display:flex; justify-content:space-between; gap:8px; }}
  figcaption span {{ color:var(--dim); font-size:11.5px; }}
  .strip {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
  .strip img {{ width:100%; border:1px solid var(--line); }}
  pre {{ margin:0; padding:12px 14px; border:1px solid var(--line);
    background:rgba(4,17,23,.7); font:12.5px/1.55 Consolas,monospace; color:#bfe7f2;
    white-space:pre-wrap; overflow-x:auto; }}
  .note {{ border:1px solid rgba(244,208,111,.32); background:rgba(40,32,10,.26);
    padding:12px 14px; font-size:13px; color:#e8dcb4; margin-top:14px; }}
  footer {{ margin-top:28px; color:var(--dim); font-size:12px; }}
  code {{ font-family:Consolas,monospace; color:var(--gold); }}
</style></head>
<body><div class="wrap"><div class="frame">

  <h1>ARC DESK <span>· studio</span></h1>
  <div class="sub">video · audio · image — rendered by <code>arcdesk/media.py</code> while
    this page was built. Every size and duration below was read back from the file.</div>

  <div class="stats">
    <div class="stat"><b>{stats['templates']}</b><i>video templates</i></div>
    <div class="stat"><b>{stats['transitions']}</b><i>transitions</i></div>
    <div class="stat"><b>{stats['vlooks']}</b><i>video looks</i></div>
    <div class="stat"><b>{stats['ilooks']}</b><i>image looks</i></div>
    <div class="stat"><b>{stats['audio']}</b><i>audio ops</i></div>
    <div class="stat"><b>{stats['reel_seconds']:.2f}s</b><i>reel rendered</i></div>
  </div>

  <h2>One photo, three grades (strength 100%)</h2>
  <div class="grid g4">{''.join(tile(n, s) for n, s in look_tiles)}</div>

  <h2>Cards at the size the platform actually wants</h2>
  <div class="grid g3">{''.join(tile(n, s, c.split(' (')[1].rstrip(')')) for n, s, c in cards)}</div>

  <h2>A rendered reel — {stats['reel_w']}×{stats['reel_h']}, {stats['reel_seconds']:.2f}s, {stats['reel_size']:.2f} MB</h2>
  <div class="strip">{''.join(f'<img src="{f}" alt="reel frame">' for f in reel_frames)}</div>
  <pre>{short(reel_reply)}</pre>

  <h2>Collage and waveform</h2>
  <div class="grid g3">
    {tile('collage 2×2', collage_img)}
    {tile('waveform PNG', wave_img)}
  </div>
  <pre>{short(collage_reply)}
{short(wave_reply)}</pre>

  <h2>Audio, measured</h2>
  <pre>{chr(10).join(short(reply) for _name, reply in audio_rows)}
{short(loudness)}</pre>

  <div class="note"><b>What this page does not do:</b> invent captions (an <code>.srt</code>
    must exist) or synthesise music (the file must exist). Both are refusals in code, not
    missing features — a generated voice-over script or a fake music bed would be a
    fabrication in the same class as a made-up fact.</div>

  <footer>{stats['templates']} video templates · {stats['transitions']} transitions ·
    {stats['vlooks']} video looks · {stats['ilooks']} image looks ·
    {stats['itemplates']} card templates · {stats['audio']} audio operations ·
    generated by <code>tools/make_studio_page.py</code>.</footer>
</div></div></body></html>"""
    return page


if __name__ == "__main__":
    if not FF:
        raise SystemExit("ffmpeg is needed to build this page")
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} — {OUT.stat().st_size / 1e6:.2f} MB")
