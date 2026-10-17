#!/usr/bin/env python3
"""Physics Studio: turn a topic JSON into a vertical 1080x1920 lesson video.

Free stack, no API keys: PIL draws the lesson cards, edge-tts voices the
narration, FFmpeg assembles the final MP4. Fully offline except the
text-to-speech call (edge-tts uses Microsoft's free neural voices).

Usage:
    python physics_studio.py video topics/example_motion.json -o out.mp4
    python physics_studio.py cards topics/example_motion.json   # cards only
    python physics_studio.py voice topics/example_motion.json   # narration only
"""
import argparse, asyncio, json, os, shutil, subprocess, sys, textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG = (12, 20, 46)          # deep navy
PANEL = (26, 36, 66)       # card row background
YELLOW = (255, 193, 7)
WHITE = (245, 247, 250)
GRAY = (148, 158, 178)
GREEN = (129, 199, 132)
RED = (239, 131, 126)


def find_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TTF from FONT_PATH, common system paths, or matplotlib's bundle."""
    candidates = [os.environ.get("FONT_PATH"), name,
                  f"/usr/share/fonts/truetype/dejavu/{name}",
                  f"/usr/share/fonts/truetype/liberation/{name}"]
    try:
        import matplotlib
        base = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        candidates += [str(base / name)]
    except Exception:
        pass
    for c in candidates:
        if c and Path(c).exists():
            return ImageFont.truetype(c, size)
    sys.exit(f"font not found: {name}. Set FONT_PATH to a .ttf file.")


def rounded(draw, box, fill, radius=28):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render_card(card: dict, fonts) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # label pill (e.g. DEFINITION, KEY IDEA)
    label = card.get("label", "").upper()
    y = 150
    if label:
        f = fonts["label"]
        tw = d.textlength(label, font=f)
        rounded(d, (110, y, 110 + tw + 72, y + 78), YELLOW, 39)
        d.text((110 + 36, y + 14), label, font=f, fill=BG)
        y += 130

    # headline
    for line in textwrap.wrap(card["title"], width=16):
        d.text((110, y), line, font=fonts["title"], fill=YELLOW)
        y += int(fonts["title"].size * 1.18)
    y += 60

    # rows: text + optional MOTION / NO MOTION style badge
    for row in card.get("rows", []):
        text = row["text"]
        badge = row.get("badge")
        tone = row.get("tone", "good")
        box_h = 118
        rounded(d, (90, y, W - 90, y + box_h), PANEL, 26)
        f = fonts["row"]
        while d.textlength(text, font=f) > W - 560 and f.size > 34:
            f = ImageFont.truetype(f.path, f.size - 2)
        d.text((140, y + (box_h - f.size) // 2 - 8), text, font=f, fill=WHITE)
        if badge:
            bf = fonts["badge"]
            tw = d.textlength(badge, font=bf)
            color = GREEN if tone == "good" else RED
            bx = W - 130 - tw - 56
            rounded(d, (bx, y + 26, bx + tw + 56, y + 92), color, 33)
            d.text((bx + 28, y + 40), badge, font=bf, fill=BG)
        y += box_h + 28

    # closing note
    if card.get("note"):
        f = fonts["note"]
        for i, line in enumerate(textwrap.wrap(card["note"], width=42)):
            d.text((110, y + 90 + i * int(f.size * 1.4)), line, font=f, fill=GRAY)
    return img


async def make_voice(text: str, voice: str, out: Path, rate: str = "+0%"):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [FF, "-i", str(path), "-f", "null", "-"],
        capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            t = line.split("Duration: ")[1].split(",")[0]
            h, m, s = t.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"could not read duration of {path}")


def ffmpeg():
    for cand in [os.environ.get("FFMPEG_PATH"), "ffmpeg",
                 "/workspace/.local/lib/python3.11/site-packages/"
                 "imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"]:
        if cand and (shutil.which(cand) or Path(cand).exists()):
            return cand
    sys.exit("ffmpeg not found. Install it or set FFMPEG_PATH.")


FF = ""  # set in build_video


def segment_from_image(image: Path, audio: Path, out: Path, pad: float = 0.5):
    dur = probe_duration(audio) + pad
    subprocess.run([FF, "-y", "-v", "error", "-loop", "1", "-i", str(image),
                    "-i", str(audio), "-t", f"{dur:.2f}",
                    "-c:v", "libx264", "-tune", "stillimage", "-r", "30",
                    "-pix_fmt", "yuv420p", "-af", "apad", "-c:a", "aac", "-b:a", "128k",
                    str(out)], check=True)


def segment_from_clip(clip: Path, audio: Path, out: Path):
    """Use a real video clip (stock or AI) as the hook, narrated over it."""
    a = probe_duration(audio)
    subprocess.run([FF, "-y", "-v", "error", "-i", str(clip), "-i", str(audio),
                    "-filter_complex",
                    "[0:v]scale=-2:1920,crop=1080:1920,fps=30,"
                    f"tpad=stop_mode=clone:stop_duration={a + 1:.2f},"
                    f"trim=duration={a:.2f},setpts=PTS-STARTPTS[v]",
                    "-map", "[v]", "-map", "1:a",
                    "-c:v", "libx264", "-crf", "19", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", str(out)],
                   check=True)


def build_video(topic: dict, work: Path, out: Path):
    global FF
    FF = ffmpeg()
    work.mkdir(parents=True, exist_ok=True)
    fonts = {k: find_font(v, s) for k, (v, s) in {
        "label": (os.environ.get("FONT_BOLD", "DejaVuSans-Bold.ttf"), 40),
        "title": (os.environ.get("FONT_BOLD", "DejaVuSans-Bold.ttf"), 84),
        "row": (os.environ.get("FONT_REG", "DejaVuSans.ttf"), 52),
        "badge": (os.environ.get("FONT_BOLD", "DejaVuSans-Bold.ttf"), 34),
        "note": (os.environ.get("FONT_REG", "DejaVuSans.ttf"), 44),
    }.items()}

    voice = topic.get("voice", "en-US-AndrewNeural")
    segs = []
    if topic.get("hook_video"):
        audio = work / "hook.mp3"
        asyncio.run(make_voice(topic["hook"]["narration"], voice, audio))
        segment_from_clip(Path(topic["hook_video"]), audio, work / "seg_000.mp4")
        segs.append(work / "seg_000.mp4")

    for i, card in enumerate(topic["cards"], start=len(segs)):
        img = render_card(card, fonts)
        png = work / f"card_{i:02d}.png"
        img.save(png)
        audio = work / f"voice_{i:02d}.mp3"
        asyncio.run(make_voice(card["narration"], voice, audio))
        seg = work / f"seg_{i:02d}.mp4"
        segment_from_image(png, audio, seg)
        segs.append(seg)

    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{s.name}'\n" for s in segs))
    subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c", "copy", str(out)], check=True)
    print(f"done: {out} ({probe_duration(out):.1f}s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["video", "cards", "voice"])
    ap.add_argument("topic", help="topic JSON file")
    ap.add_argument("-o", "--out", default="out.mp4")
    args = ap.parse_args()
    topic = json.loads(Path(args.topic).read_text())
    work = Path("_studio_build")
    if args.command == "video":
        build_video(topic, work, Path(args.out))
    else:
        raise SystemExit("cards/voice-only mode: coming in v1.1, use video")


if __name__ == "__main__":
    main()
