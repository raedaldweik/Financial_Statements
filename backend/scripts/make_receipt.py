"""One-time generator for the bundled transfer-confirmation screenshot
(demo_data/receipt.jpg) — a mobile-banking "transfer successful" screen.

Run from the backend/ directory:  python scripts/make_receipt.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "demo_data" / "receipt.jpg"
FONT_DIR = "/usr/share/fonts/truetype/dejavu"

W, H = 720, 1500
NAVY = (11, 37, 69)
GOLD = (200, 164, 74)
GREEN = (28, 150, 88)
TEXT = (24, 30, 40)
MUTED = (110, 118, 130)
LINE = (226, 230, 236)
BG = (244, 246, 249)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(f"{FONT_DIR}/DejaVuSans{'-Bold' if bold else ''}.ttf", size)


def build() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # status bar + app header
    d.rectangle([0, 0, W, 150], fill=NAVY)
    d.text((28, 16), "09:41", font=font(18, True), fill="white")
    d.text((W - 118, 16), "5G  ▮▮▮  84%", font=font(16), fill="white")
    d.text((28, 70), "‹", font=font(34, True), fill="white")
    d.text((70, 76), "EXAMPLE BANK", font=font(22, True), fill=GOLD)
    d.text((70, 106), "Transfer confirmation", font=font(16), fill=(200, 210, 225))

    # success tick
    cx, cy = W // 2, 265
    d.ellipse([cx - 58, cy - 58, cx + 58, cy + 58], fill=GREEN)
    d.line([(cx - 26, cy + 2), (cx - 8, cy + 20), (cx + 28, cy - 22)], fill="white", width=9, joint="curve")
    d.text((cx, cy + 92), "Transfer successful", font=font(28, True), fill=TEXT, anchor="mm")
    d.text((cx, cy + 128), "24 Aug 2026, 09:39", font=font(17), fill=MUTED, anchor="mm")

    # amount card
    top = 440
    d.rounded_rectangle([32, top, W - 32, top + 130], radius=18, fill="white", outline=LINE)
    d.text((cx, top + 40), "AMOUNT", font=font(13, True), fill=MUTED, anchor="mm")
    d.text((cx, top + 84), "AED 12,500.00", font=font(40, True), fill=NAVY, anchor="mm")

    rows = [
        ("Beneficiary", "MUBARAK SALEM"),
        ("Account number", "5660609"),
        ("IBAN", "AE60 0340 0056 6060 9"),
        ("Beneficiary bank", "Example Bank"),
        ("Purpose", "Purchase of electronic devices"),
        None,
        ("From account", "AHMED HASSAN"),
        ("", "Current Account ••7712045"),
        None,
        ("Transfer type", "Local transfer — instant"),
        ("Transaction reference", "TRX-2026-0824-4821"),
        ("Transaction fee", "AED 0.00"),
        ("Status", "Completed"),
    ]
    y = top + 160
    d.rounded_rectangle([32, y, W - 32, y + 40 + 54 * sum(1 for r in rows if r) + 14 * sum(1 for r in rows if r is None)],
                        radius=18, fill="white", outline=LINE)
    y += 22
    for r in rows:
        if r is None:
            d.line([(56, y + 6), (W - 56, y + 6)], fill=LINE, width=1)
            y += 14
            continue
        label, value = r
        d.text((56, y + 8), label, font=font(15), fill=MUTED)
        f = font(17, True) if label in ("Beneficiary", "IBAN", "Transaction reference", "Status") else font(17)
        colour = GREEN if label == "Status" else TEXT
        d.text((W - 56, y + 8), value, font=f, fill=colour, anchor="ra")
        y += 54

    # buttons
    y += 46
    d.rounded_rectangle([32, y, W - 32, y + 66], radius=14, fill=NAVY)
    d.text((cx, y + 33), "Share receipt", font=font(19, True), fill="white", anchor="mm")
    y += 84
    d.rounded_rectangle([32, y, W - 32, y + 66], radius=14, fill="white", outline=NAVY, width=2)
    d.text((cx, y + 33), "Done", font=font(19, True), fill=NAVY, anchor="mm")

    img.save(OUT, "JPEG", quality=88)
    print(f"Wrote {OUT}  ({img.width}x{img.height})")


if __name__ == "__main__":
    build()
