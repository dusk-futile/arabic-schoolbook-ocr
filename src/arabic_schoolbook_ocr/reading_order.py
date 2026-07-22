from __future__ import annotations

from collections.abc import Iterable
from statistics import median

from .schemas import OcrBlock


def _has_parallel_columns(blocks: list[OcrBlock]) -> bool:
    """Detect horizontally separated blocks that occupy the same vertical band."""

    for index, first in enumerate(blocks):
        for second in blocks[index + 1 :]:
            vertical_overlap = max(
                0.0,
                min(first.bbox.bottom, second.bbox.bottom) - max(first.bbox.y, second.bbox.y),
            )
            minimum_height = min(first.bbox.height, second.bbox.height)
            horizontal_overlap = max(
                0.0,
                min(first.bbox.right, second.bbox.right) - max(first.bbox.x, second.bbox.x),
            )
            if minimum_height > 0 and vertical_overlap >= minimum_height * 0.25:
                if horizontal_overlap <= min(first.bbox.width, second.bbox.width) * 0.15:
                    return True
    return False


def _cluster_columns(blocks: list[OcrBlock], page_width: float) -> list[list[OcrBlock]]:
    if not blocks:
        return []
    if not _has_parallel_columns(blocks):
        return [sorted(blocks, key=lambda block: (block.bbox.y, -block.bbox.x))]
    centers = sorted(
        ((block.bbox.x + block.bbox.width / 2, block) for block in blocks),
        key=lambda item: item[0],
        reverse=True,
    )
    typical_width = median(block.bbox.width for block in blocks)
    threshold = max(page_width * 0.12, typical_width * 0.35)
    columns: list[list[OcrBlock]] = []
    column_centers: list[float] = []
    for center, block in centers:
        match = next(
            (
                index
                for index, existing_center in enumerate(column_centers)
                if abs(center - existing_center) <= threshold
            ),
            None,
        )
        if match is None:
            columns.append([block])
            column_centers.append(center)
        else:
            columns[match].append(block)
            column_centers[match] = sum(
                item.bbox.x + item.bbox.width / 2 for item in columns[match]
            ) / len(columns[match])
    paired = sorted(
        zip(column_centers, columns, strict=True), reverse=True, key=lambda pair: pair[0]
    )
    return [sorted(column, key=lambda block: (block.bbox.y, -block.bbox.x)) for _, column in paired]


def reading_order_rtl(blocks: Iterable[OcrBlock], page_width: float) -> list[OcrBlock]:
    """Order full-width separators and right-to-left columns without reversing text."""

    remaining = sorted(list(blocks), key=lambda block: (block.bbox.y, -block.bbox.x))
    if len(remaining) <= 1:
        return remaining
    spanning = [block for block in remaining if block.bbox.width >= page_width * 0.68]
    if not spanning:
        return [block for column in _cluster_columns(remaining, page_width) for block in column]

    ordered: list[OcrBlock] = []
    band_start = 0.0
    for separator in spanning:
        band = [
            block
            for block in remaining
            if block is not separator and band_start <= block.bbox.y < separator.bbox.y
        ]
        ordered.extend(block for column in _cluster_columns(band, page_width) for block in column)
        ordered.append(separator)
        band_start = separator.bbox.bottom
    tail = [
        block
        for block in remaining
        if block not in ordered and block not in spanning and block.bbox.y >= band_start
    ]
    ordered.extend(block for column in _cluster_columns(tail, page_width) for block in column)
    for block in remaining:
        if block not in ordered:
            ordered.append(block)
    return ordered
