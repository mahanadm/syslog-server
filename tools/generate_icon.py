"""Generate the Syslog Server .ico file with multiple resolutions."""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

SIZES = [16, 32, 48, 64, 256]
OUTPUT = os.path.join(
    os.path.dirname(__file__), "..", "src", "syslog_server", "assets", "syslog_server.ico"
)


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark blue-gray circle background
    margin = max(1, size // 16)
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(30, 41, 59, 255),
    )

    # Blue "S" letter centered
    font_size = int(size * 0.55)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), "S", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    draw.text((x, y), "S", fill=(96, 165, 250, 255), font=font)

    return img


def main():
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    images = [draw_icon(s) for s in SIZES]
    images[0].save(
        OUTPUT,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[1:],
    )
    print(f"Icon saved to {os.path.abspath(OUTPUT)}")


if __name__ == "__main__":
    main()
