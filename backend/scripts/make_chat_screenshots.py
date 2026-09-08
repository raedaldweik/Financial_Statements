"""One-time generator for the demo complaint evidence: WhatsApp-style
screenshots of the conversation in demo_data/conversation.txt.

Run from the backend/ directory:  python scripts/make_chat_screenshots.py
Requires:  pip install Pillow
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent / "demo_data"
FONT_DIR = "/usr/share/fonts/truetype/dejavu"

W = 480
PAD = 12
BUBBLE_MAX = int(W * 0.76)

BG = (11, 20, 26)          # WhatsApp dark background
HEADER = (31, 44, 52)
BUBBLE_IN = (31, 44, 52)
BUBBLE_OUT = (0, 92, 75)
TEXT = (233, 237, 239)
TIME = (134, 150, 160)
CHIP = (24, 33, 41)
GREEN = (0, 168, 132)

F = ImageFont.truetype(f"{FONT_DIR}/DejaVuSans.ttf", 15)
F_SMALL = ImageFont.truetype(f"{FONT_DIR}/DejaVuSans.ttf", 11)
F_BOLD = ImageFont.truetype(f"{FONT_DIR}/DejaVuSans-Bold.ttf", 16)

LINE_RE = re.compile(r"^(\d{2}/\d{2}/\d{4}), (\d{2}:\d{2}) - ([^:]+): (.*)$")
EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿️⏳✅🙏😊]")


def parse() -> list[dict]:
    msgs = []
    for raw in (BASE / "conversation.txt").read_text(encoding="utf-8").splitlines():
        m = LINE_RE.match(raw.strip())
        if not m:
            continue
        date, time, sender, text = m.groups()
        text = EMOJI_RE.sub("", text).strip()
        if "(file attached)" in text:
            text = "[ Photo — transfer receipt ]"
        msgs.append({"date": date, "time": time,
                     "out": sender.startswith("Sara"), "text": text})
    return msgs


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines = []
    for para in text.split("\n"):
        words, cur = para.split(" "), ""
        for w in words:
            trial = (cur + " " + w).strip()
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def measure(draw, msg) -> tuple[list[str], int, int]:
    lines = wrap(draw, msg["text"], F, BUBBLE_MAX - 24)
    w = max([draw.textlength(l, font=F) for l in lines] + [40])
    time_w = draw.textlength(msg["time"], font=F_SMALL)
    bw = int(min(BUBBLE_MAX, max(w, time_w) + 24))
    bh = len(lines) * 20 + 14 + 14
    return lines, bw, bh


def render(msgs: list[dict], out: Path, contact: str, number: str) -> None:
    # First pass: compute height
    probe = ImageDraw.Draw(Image.new("RGB", (W, 100)))
    y = 64 + 10
    last_date = None
    heights = []
    for msg in msgs:
        chip = msg["date"] != last_date
        last_date = msg["date"]
        lines, bw, bh = measure(probe, msg)
        y += (34 if chip else 0) + bh + 8
        heights.append((chip, lines, bw, bh))
    H = y + 12

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Header
    d.rectangle([0, 0, W, 64], fill=HEADER)
    d.text((16, 22), "‹", font=F_BOLD, fill=TIME)
    d.ellipse([36, 14, 72, 50], fill=(64, 80, 92))
    d.text((47, 22), contact[0], font=F_BOLD, fill=TEXT)
    d.text((84, 15), contact, font=F_BOLD, fill=TEXT)
    d.text((84, 36), number, font=F_SMALL, fill=TIME)

    y = 64 + 10
    last_date = None
    for msg, (chip, lines, bw, bh) in zip(msgs, heights):
        if chip:
            label = msg["date"]
            lw = d.textlength(label, font=F_SMALL) + 20
            d.rounded_rectangle([(W - lw) / 2, y + 6, (W + lw) / 2, y + 28],
                                radius=6, fill=CHIP)
            d.text(((W - lw) / 2 + 10, y + 11), label, font=F_SMALL, fill=TIME)
            y += 34
        x0 = W - PAD - bw if msg["out"] else PAD
        fill = BUBBLE_OUT if msg["out"] else BUBBLE_IN
        d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=10, fill=fill)
        ty = y + 8
        for line in lines:
            d.text((x0 + 12, ty), line, font=F, fill=TEXT)
            ty += 20
        stamp = msg["time"] + ("  ✓✓" if msg["out"] else "")
        d.text((x0 + bw - d.textlength(stamp, font=F_SMALL) - 10, y + bh - 17),
               stamp, font=F_SMALL, fill=TIME)
        y += bh + 8

    img.save(out)
    print(f"Wrote {out}  ({img.width}x{img.height})")


def main() -> None:
    msgs = parse()
    # split into 3 screenshots at natural narrative breaks
    cuts = [0, 12, 23, len(msgs)]
    for i in range(3):
        render(msgs[cuts[i]:cuts[i + 1]], BASE / f"chat_{i + 1}.png",
               "LuxeTime Khalid", "+971 52 884 7719")


if __name__ == "__main__":
    main()
