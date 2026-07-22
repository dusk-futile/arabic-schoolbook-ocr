from __future__ import annotations

from pathlib import Path

from PIL import ImageDraw, ImageFont
from PIL.Image import Image

from .schemas import CanonicalBlock, LayoutRegion

_COLORS = ["#0f766e", "#2563eb", "#d97706", "#be123c", "#7c3aed", "#0891b2"]


def _font(size: int = 22) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    arial = Path("C:/Windows/Fonts/arial.ttf")
    return ImageFont.truetype(str(arial), size) if arial.is_file() else ImageFont.load_default()


def draw_layout_overlay(image: Image, regions: list[LayoutRegion]) -> Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    font = _font()
    for index, region in enumerate(regions):
        color = _COLORS[index % len(_COLORS)]
        box = region.bbox
        draw.rectangle((box.x, box.y, box.right, box.bottom), outline=color, width=5)
        draw.text((box.x + 5, box.y + 5), region.block_type.value, fill=color, font=font)
    return overlay


def draw_reading_order_overlay(image: Image, blocks: list[CanonicalBlock]) -> Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    font = _font(28)
    for block in sorted(blocks, key=lambda item: item.reading_order):
        color = _COLORS[block.reading_order % len(_COLORS)]
        box = block.bbox
        draw.rectangle((box.x, box.y, box.right, box.bottom), outline=color, width=5)
        draw.ellipse((box.x, box.y, box.x + 42, box.y + 42), fill=color)
        draw.text((box.x + 12, box.y + 5), str(block.reading_order + 1), fill="white", font=font)
    return overlay
