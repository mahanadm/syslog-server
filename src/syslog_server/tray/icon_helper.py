"""Icon loading and status-variant generation for the tray."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def _assets_dir() -> Path:
    return Path(__file__).parent.parent / "assets"


def load_icon() -> Image.Image:
    """Load the main icon from assets, or generate a fallback."""
    ico_path = _assets_dir() / "syslog_server.ico"
    if ico_path.exists():
        img = Image.open(ico_path)
        # Pick the largest size available and resize to 64x64
        img = img.resize((64, 64), Image.Resampling.LANCZOS)
        return img.convert("RGBA")
    return _generate_fallback(64)


def make_status_icon(base: Image.Image, running: bool) -> Image.Image:
    """Overlay a small green (running) or red (stopped) dot on the base icon."""
    img = base.copy()
    draw = ImageDraw.Draw(img)
    size = img.width
    dot_r = size // 6
    x = size - dot_r - 1
    y = size - dot_r - 1
    color = (34, 197, 94) if running else (239, 68, 68)  # green / red
    draw.ellipse(
        [x - dot_r, y - dot_r, x + dot_r, y + dot_r],
        fill=color,
        outline=(0, 0, 0),
    )
    return img


def _generate_fallback(size: int) -> Image.Image:
    """Generate a simple icon if the .ico file is missing."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(1, size // 16)
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(30, 41, 59, 255))
    # Simple "S" text
    font_size = int(size * 0.55)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", font_size)
    except (OSError, ImportError):
        from PIL import ImageFont
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "S", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    draw.text((x, y), "S", fill=(96, 165, 250, 255), font=font)
    return img
