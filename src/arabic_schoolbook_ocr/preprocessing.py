from __future__ import annotations

from dataclasses import dataclass

from PIL import ImageFilter, ImageOps
from PIL.Image import Image

from .schemas import BoundingBox


@dataclass(frozen=True)
class PreprocessConfig:
    autocontrast_cutoff: float = 0.5
    median_filter_size: int = 3
    preserve_color: bool = False


def preprocess_page(image: Image, config: PreprocessConfig | None = None) -> Image:
    """Apply a deterministic, offline preprocessing pass without changing geometry."""

    selected = config or PreprocessConfig()
    working = image.convert("RGB")
    if selected.preserve_color:
        channels = [
            ImageOps.autocontrast(channel, cutoff=selected.autocontrast_cutoff)
            for channel in working.split()
        ]
        working = __import__("PIL.Image", fromlist=["merge"]).merge("RGB", channels)
    else:
        gray = ImageOps.grayscale(working)
        gray = ImageOps.autocontrast(gray, cutoff=selected.autocontrast_cutoff)
        working = gray.convert("RGB")
    if selected.median_filter_size > 1:
        working = working.filter(ImageFilter.MedianFilter(selected.median_filter_size))
    return working


def recrop_high_resolution(image: Image, bbox: BoundingBox, *, scale: int = 2) -> Image:
    if bbox.coordinate_space == "normalized":
        left = round(bbox.x * image.width)
        top = round(bbox.y * image.height)
        right = round((bbox.x + bbox.width) * image.width)
        bottom = round((bbox.y + bbox.height) * image.height)
    else:
        left, top, right, bottom = (
            round(bbox.x),
            round(bbox.y),
            round(bbox.right),
            round(bbox.bottom),
        )
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    crop = image.crop((left, top, max(left + 1, right), max(top + 1, bottom)))
    if scale <= 1:
        return crop
    return crop.resize((crop.width * scale, crop.height * scale))
