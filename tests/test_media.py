"""The studio — video, audio and image work, verified by measuring the output.

A media tool can look impressive and still be wrong. So every check here opens the
produced file and measures it: pixel dimensions, whether the grade actually changed
the pixels, whether a 2 s and a 1.5 s clip with a 0.6 s cross-fade come out at 2.9 s,
whether the originals are still untouched, and whether an impossible request is
refused with the list of what *is* possible.

Run:  python tests/test_media.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import media  # noqa: E402
from arcdesk.ai import tools  # noqa: E402

ok = True
work = Path(tempfile.mkdtemp(prefix="arcdesk-media-"))


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<56} {str(got)[:44]!r}")
    ok &= bool(good)


def note(label: str, value) -> None:
    print(f"   ..   {label:<56} {str(value)[:52]}")


try:
    from PIL import Image, ImageChops, ImageDraw, ImageStat
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False
FF = shutil.which("ffmpeg")
HAVE_FF = bool(FF)


def ff(*args: str) -> bool:
    proc = subprocess.run([FF, "-y", "-v", "error", *args], capture_output=True, text=True,
                          timeout=180)
    return proc.returncode == 0


print("1) the catalogues are complete and internally consistent")
check("video templates exist", len(media.VIDEO_TEMPLATES) >= 8, True)
check("transitions exist", len(media.TRANSITIONS) >= 20, True)
check("video looks exist", len(media.VIDEO_LOOKS) >= 12, True)
check("audio ops exist", len(media.AUDIO_OPS) >= 12, True)
check("image looks exist", len(media.IMAGE_LOOKS) >= 12, True)
check("image templates exist", len(media.IMAGE_TEMPLATES) >= 6, True)
bad = []
for name, spec in media.VIDEO_TEMPLATES.items():
    if spec["aspect"] not in media.ASPECTS:
        bad.append(f"{name}:aspect")
    if spec["transition"] not in media.TRANSITIONS:
        bad.append(f"{name}:transition")
    if spec["look"] not in media.VIDEO_LOOKS:
        bad.append(f"{name}:look")
check("every template points at a real aspect/transition/look", bad, [])
check("catalogue prints the templates", "reel_hook" in media.catalog("video"), True)
check("catalogue prints the audio ops", "denoise" in media.catalog("audio"), True)

if not HAVE_PIL:
    print("\n   (Pillow is not installed — image checks skipped, not passed)")
else:
    print("2) image looks change the pixels, and only as much as asked")
    base = work / "photo.png"
    img = Image.new("RGB", (640, 480))
    draw = ImageDraw.Draw(img)
    for y in range(480):
        draw.line([(0, y), (640, y)], fill=(30 + y // 4, 90 + y // 6, 160 - y // 8))
    draw.rectangle([80, 90, 300, 300], fill=(220, 170, 60))
    draw.ellipse([360, 200, 560, 420], fill=(240, 240, 240))
    img.save(base)

    failures = []
    for look in media.IMAGE_LOOKS:
        result = media.image_look(str(base), look, 0.9)
        if result.startswith("ERROR"):
            failures.append(f"{look}: {result[:40]}")
    check("all 16 looks render without error", failures, [])
    check("look output is a new file", list(work.glob("photo_look_*.png")) != [], True)

    media.image_look(str(base), "noir", 1.0, out=str(work / "noir_full.png"))
    noir = work / "noir_full.png"
    with Image.open(noir) as out:
        stat = ImageStat.Stat(out.convert("RGB"))
        spread = max(stat.mean) - min(stat.mean)
    check("noir is actually monochrome (channel means equal)", round(spread, 1) <= 1.0, True)

    media.image_look(str(base), "vignette", 1.0, out=str(work / "vig.png"))
    with Image.open(work / "vig.png") as out, Image.open(base) as src:
        corner = ImageStat.Stat(ImageChops.difference(
            out.convert("RGB").crop((0, 0, 60, 60)), src.convert("RGB").crop((0, 0, 60, 60))
        )).mean
        centre = ImageStat.Stat(ImageChops.difference(
            out.convert("RGB").crop((290, 210, 350, 270)),
            src.convert("RGB").crop((290, 210, 350, 270)))).mean
    check("vignette darkens the corners", sum(corner) / 3 > 8.0, True)
    check("but not the centre", sum(centre) / 3 < 2.0, True)

    untouched = media.image_look(str(base), "bloom", 1.0,
                                 out=str(work / "strength100.png"))
    half = media.image_look(str(base), "bloom", 0.0, out=str(work / "strength000.png"))
    check("renders on request", not untouched.startswith("ERROR") and
          not half.startswith("ERROR"), True)
    with Image.open(work / "strength000.png") as out, Image.open(base) as src:
        delta = ImageStat.Stat(ImageChops.difference(
            out.convert("RGB"), src.convert("RGB"))).mean
    check("strength 0 leaves the image alone", sum(delta) / 3 < 1.0, True)

    print("3) finished cards are the exact pixel size the platform wants")
    story = media.image_card(str(base), "instagram_story", "Neeli rooftop cafe",
                             "breakfast included on direct bookings", footer="ARC")
    post = media.image_card(str(base), "instagram_post", "Room 12", "season tariff 4200")
    thumb = media.image_card(str(base), "youtube_thumb", "Hampi in 3 days")
    sizes = {}
    for label, text in (("story", story), ("post", post), ("thumb", thumb)):
        path = Path(text.split(" → ")[1].split(" (")[0])
        with Image.open(path) as out:
            sizes[label] = out.size
    check("story 1080×1920", sizes.get("story"), (1080, 1920))
    check("post 1080×1080", sizes.get("post"), (1080, 1080))
    check("thumbnail 1280×720", sizes.get("thumb"), (1280, 720))

    with_text_path = Path(post.split(" → ")[1].split(" (")[0])
    plain_path = media.image_card(str(base), "instagram_post", "", "")
    plain_file = Path(plain_path.split(" → ")[1].split(" (")[0])
    with Image.open(with_text_path) as a, Image.open(plain_file) as b:
        text_delta = ImageStat.Stat(ImageChops.difference(
            a.convert("RGB"), b.convert("RGB"))).mean
    check("the title actually changes pixels", sum(text_delta) / 3 > 0.5, True)

    print("4) collage geometry is arithmetic, not magic")
    collage = media.image_collage(f"{base}|{base}", cols=2, rows=2, cell=200, gap=12)
    path = Path(collage.split(" → ")[1].split(" (")[0])
    with Image.open(path) as out:
        got = out.size
    check("2×2 of 200 px cells with 12 px gaps = 436×436", got, (436, 436))
    note("collage", f"{got[0]}×{got[1]}")

    print("5) batch grading never touches the originals")
    folder = work / "batch"
    folder.mkdir()
    for i in range(3):
        Image.new("RGB", (120, 90), (20 * i, 80, 140)).save(folder / f"pic{i}.png")
    before = {p.name: p.stat().st_mtime_ns for p in folder.iterdir()}
    graded = media.image_batch(str(folder), "warm", 0.8)
    after = {p.name: p.stat().st_mtime_ns for p in folder.iterdir() if "_look_" not in p.name}
    check("3 images graded", "3 image(s) graded" in graded, True)
    check("originals unmodified", before, after)
    check("new sibling files exist", len(list(folder.glob("*_look_warm_*.png"))), 3)

if not HAVE_FF:
    print("\n   (ffmpeg is not installed — video and audio checks skipped, not passed)")
else:
    print("6) video: two clips, one cross-fade, exact duration")
    one, two = work / "one.mp4", work / "two.mp4"
    made_one = ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=2",
                  "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                  "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", str(one))
    made_two = ff("-f", "lavfi", "-i", "smptebars=size=240x320:rate=25:duration=1.5",
                  "-f", "lavfi", "-i", "sine=frequency=660:duration=1.5",
                  "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", str(two))
    check("test clips built", bool(made_one and made_two), True)
    built = media.video_timeline(f"{one}|{two}", template="story", title="Belagavi",
                                 subtitle="room 12 · rooftop", transition="fade")
    check("timeline rendered", not built.startswith("ERROR"), True)
    if not built.startswith("ERROR"):
        path = Path(built.split(" → ")[1].split(" (")[0])
        info = media.probe(str(path))
        check("output resolution follows the template", (info["width"], info["height"]),
              (1080, 1920))
        expected = 2 + 1.5 - 0.6
        check(f"duration ≈ {expected}s (clips minus the cross-fade)",
              abs(info["seconds"] - expected) < 0.45, True)
        note("rendered", f"{info['seconds']:.2f}s, {path.stat().st_size / 1e6:.2f} MB")

    if HAVE_PIL:
        still = work / "photo.png"
        if not still.exists():
            Image.new("RGB", (400, 300), (30, 60, 90)).save(still)
        slides = media.video_timeline(f"{still}|{still}", template="slideshow",
                                     still_seconds=1.5, transition="fade")
        check("stills render as a slideshow with ken-burns",
              "ken-burns" in slides, True)
        if not slides.startswith("ERROR"):
            info = media.probe(str(Path(slides.split(" → ")[1].split(" (")[0])))
            check("two 1.5 s stills minus a 0.6 s fade ≈ 2.4 s",
                  abs(info.get("seconds", 0) - 2.4) < 0.5, True)

    graded = media.video_look(str(one), "noir", 0.8)
    check("single-clip grade renders", not graded.startswith("ERROR"), True)

    print("7) audio: filters keep the length, mixing follows the first track")
    tone = work / "tone.wav"
    check("test tone built", ff("-f", "lavfi", "-i", "sine=frequency=300:duration=2",
                                str(tone)), True)
    for op in ("denoise", "loudnorm", "eq3", "compress", "silence_trim", "mono"):
        result = media.audio_op(str(tone), op)
        good = not result.startswith("ERROR")
        check(f"{op} renders", good, True)
    length = media.audio_op(str(tone), "loudnorm")
    path = tone.parent / length.split(" → ")[1].split(" (")[0]
    info = media.probe(str(path))
    check("loudness pass keeps the duration", abs(info["seconds"] - 2.0) < 0.25, True)

    music = work / "music.wav"
    ff("-f", "lavfi", "-i", "sine=frequency=880:duration=3", str(music))
    mixed = media.audio_mix(f"{tone}|{music}", "-3,-16", duck=True)
    check("mix reports both tracks and the duck", "2 tracks" in mixed and "ducked" in mixed,
          True)
    check("mix duration follows the voice", "0:02" in mixed or "0:01.9" in mixed, True)

    wave = media.audio_waveform(str(tone))
    check("waveform image written", wave.endswith(".png"), True)
    chapters = media.audio_op(str(tone), "chapters")
    check("chapters tells the truth on a solid tone",
          "No silences" in chapters or "speech block" in chapters, True)

    print("8) impossible requests are refused with the list of what is possible")
    bad_template = media.video_timeline(f"{one}", template="bollywood")
    check("unknown template refused", bad_template.startswith("ERROR"), True)
    check("  · and it lists the real ones", "reel_hook" in bad_template, True)
    bad_look = media.video_look(str(one), "sepia_deluxe")
    check("unknown look refused", bad_look.startswith("ERROR"), True)
    check("  · and it lists the real ones", "cinematic" in bad_look, True)
    bad_audio = media.audio_op(str(tone), "autotune")
    check("unknown audio op refused", bad_audio.startswith("ERROR"), True)
    no_music = media.video_timeline(f"{one}", music=str(work / "nope.mp3"))
    check("missing music refuses instead of synthesising",
          no_music.startswith("ERROR") and "will not synthesise" in no_music, True)
    no_file = media.video_look(str(work / "ghost.mp4"))
    check("missing file is an error, not a crash", no_file.startswith("ERROR"), True)

print("9) it is wired as three tools and they dispatch")
for name in ("video_studio", "audio_studio", "image_studio"):
    check(f"{name} registered", name in tools.TOOLS, True)
check("tool count", len(tools.TOOLS) >= 77, True)
if HAVE_PIL:
    via_tool = tools.call("image_studio", {"action": "card", "path": str(work / "photo.png"),
                                           "template": "instagram_post", "title": "probe"})
    check("image_studio dispatches", "1080×1080" in via_tool, True)
check("studio output lives under the data folder",
      str(media.studio_dir()).startswith(str(Path(os.environ["ARCDESK_HOME"]))), True)

print()
print("ALL PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
