from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from typing import Any

from .schemas import BlockType, BoundingBox, CanonicalBlock, CanonicalPage

_ENGLISH_TOKEN = re.compile(r"[A-Za-z]+(?:[A-Za-z0-9./%+-]*[A-Za-z0-9])?")
_DIGIT_TOKEN = re.compile(r"[0-9\u0660-\u0669]+(?:[.,\u066B\u066C][0-9\u0660-\u0669]+)?")


def edit_distance(reference: Sequence[Any], hypothesis: Sequence[Any]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row_index, reference_item in enumerate(reference, start=1):
        current = [row_index]
        for column_index, hypothesis_item in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column_index] + 1,
                    previous[column_index - 1] + (reference_item != hypothesis_item),
                )
            )
        previous = current
    return previous[-1]


def _text(page: CanonicalPage, *, corrected: bool) -> str:
    blocks = sorted(page.blocks, key=lambda block: block.reading_order)
    return "\n".join(
        (
            block.approved_corrected_text
            if corrected and block.approved_corrected_text is not None
            else block.literal_text
        )
        for block in blocks
    )


def _safe_rate(errors: int, total: int) -> float | None:
    return errors / total if total else None


def _token_accuracy(reference: list[str], hypothesis: list[str]) -> float | None:
    if not reference:
        return None
    errors = edit_distance(reference, hypothesis)
    return max(0.0, 1 - errors / len(reference))


def _f1(reference: Counter[str], hypothesis: Counter[str]) -> float | None:
    true_positive = sum((reference & hypothesis).values())
    false_positive = sum((hypothesis - reference).values())
    false_negative = sum((reference - hypothesis).values())
    if true_positive + false_positive + false_negative == 0:
        return None
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
    )
    return 2 * precision * recall / (precision + recall) if precision + recall else 0


def _iou(first: BoundingBox, second: BoundingBox) -> float:
    overlap_width = max(0.0, min(first.right, second.right) - max(first.x, second.x))
    overlap_height = max(0.0, min(first.bottom, second.bottom) - max(first.y, second.y))
    intersection = overlap_width * overlap_height
    union = first.width * first.height + second.width * second.height - intersection
    return intersection / union if union else 0.0


def _geometry_matches(
    reference: list[CanonicalBlock], hypothesis: list[CanonicalBlock]
) -> dict[str, CanonicalBlock]:
    candidates = sorted(
        (
            (_iou(reference_block.bbox, hypothesis_block.bbox), reference_block, hypothesis_block)
            for reference_block in reference
            for hypothesis_block in hypothesis
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    matches: dict[str, CanonicalBlock] = {}
    used_hypothesis: set[str] = set()
    for score, reference_block, hypothesis_block in candidates:
        if score < 0.05:
            break
        if reference_block.id in matches or hypothesis_block.id in used_hypothesis:
            continue
        matches[reference_block.id] = hypothesis_block
        used_hypothesis.add(hypothesis_block.id)
    return matches


def _reading_order_accuracy(
    reference: list[CanonicalBlock],
    hypothesis: list[CanonicalBlock],
    matches: dict[str, CanonicalBlock],
) -> float | None:
    ordered_reference = sorted(reference, key=lambda block: block.reading_order)
    if not ordered_reference:
        return None
    if len(ordered_reference) == 1:
        return 1.0 if ordered_reference[0].id in matches else 0.0
    hypothesis_ranks = {
        block.id: rank
        for rank, block in enumerate(sorted(hypothesis, key=lambda block: block.reading_order))
    }
    correct = 0
    comparisons = 0
    for left_index, left in enumerate(ordered_reference):
        for right in ordered_reference[left_index + 1 :]:
            comparisons += 1
            left_match = matches.get(left.id)
            right_match = matches.get(right.id)
            if (
                left_match is not None
                and right_match is not None
                and hypothesis_ranks[left_match.id] < hypothesis_ranks[right_match.id]
            ):
                correct += 1
    return correct / comparisons if comparisons else None


def _table_preservation(
    reference: list[CanonicalBlock], matches: dict[str, CanonicalBlock]
) -> tuple[float | None, float | None]:
    total_rows = 0
    preserved_rows = 0
    total_cells = 0
    preserved_cells = 0
    for reference_block in reference:
        if reference_block.table is None:
            continue
        total_rows += reference_block.table.rows
        total_cells += len(reference_block.table.cells)
        hypothesis_block = matches.get(reference_block.id)
        if hypothesis_block is None or hypothesis_block.table is None:
            continue
        hypothesis_cells = {
            (cell.row, cell.column): unicodedata.normalize("NFC", cell.text).strip()
            for cell in hypothesis_block.table.cells
        }
        reference_rows: dict[int, list[tuple[tuple[int, int], str]]] = {}
        for cell in reference_block.table.cells:
            key = (cell.row, cell.column)
            text = unicodedata.normalize("NFC", cell.text).strip()
            reference_rows.setdefault(cell.row, []).append((key, text))
            if hypothesis_cells.get(key) == text:
                preserved_cells += 1
        for row in range(reference_block.table.rows):
            cells = reference_rows.get(row, [])
            if row < hypothesis_block.table.rows and all(
                hypothesis_cells.get(key) == text for key, text in cells
            ):
                preserved_rows += 1
    return (
        preserved_rows / total_rows if total_rows else None,
        preserved_cells / total_cells if total_cells else None,
    )


def calculate_page_metrics(
    ground_truth: CanonicalPage,
    hypothesis: CanonicalPage,
    *,
    human_reviewed: bool,
) -> dict[str, float | int | None]:
    if not human_reviewed:
        raise ValueError("Accuracy metrics require fully human-corrected ground truth")
    reference_text = unicodedata.normalize("NFC", _text(ground_truth, corrected=True))
    hypothesis_text = unicodedata.normalize("NFC", _text(hypothesis, corrected=False))
    reference_words = reference_text.split()
    hypothesis_words = hypothesis_text.split()
    reference_digits = _DIGIT_TOKEN.findall(reference_text)
    hypothesis_digits = _DIGIT_TOKEN.findall(hypothesis_text)
    reference_english = _ENGLISH_TOKEN.findall(reference_text)
    hypothesis_english = _ENGLISH_TOKEN.findall(hypothesis_text)
    reference_punctuation = [
        char for char in reference_text if unicodedata.category(char).startswith("P")
    ]
    hypothesis_punctuation = [
        char for char in hypothesis_text if unicodedata.category(char).startswith("P")
    ]
    reference_headings = Counter(
        block.approved_corrected_text or block.unicode_normalized_text
        for block in ground_truth.blocks
        if block.block_type
        in {
            BlockType.DOCUMENT_TITLE,
            BlockType.CHAPTER_TITLE,
            BlockType.HEADING_1,
            BlockType.HEADING_2,
            BlockType.HEADING_3,
        }
    )
    hypothesis_headings = Counter(
        block.unicode_normalized_text
        for block in hypothesis.blocks
        if block.block_type
        in {
            BlockType.DOCUMENT_TITLE,
            BlockType.CHAPTER_TITLE,
            BlockType.HEADING_1,
            BlockType.HEADING_2,
            BlockType.HEADING_3,
        }
    )
    reference_boundaries = Counter(
        decision.boundary.value for block in ground_truth.blocks for decision in block.boundaries
    )
    hypothesis_boundaries = Counter(
        decision.boundary.value for block in hypothesis.blocks for decision in block.boundaries
    )
    matches = _geometry_matches(ground_truth.blocks, hypothesis.blocks)
    table_row_preservation, table_cell_preservation = _table_preservation(
        ground_truth.blocks, matches
    )
    return {
        "cer": _safe_rate(edit_distance(reference_text, hypothesis_text), len(reference_text)),
        "wer": _safe_rate(edit_distance(reference_words, hypothesis_words), len(reference_words)),
        "digit_accuracy": _token_accuracy(reference_digits, hypothesis_digits),
        "english_token_accuracy": _token_accuracy(reference_english, hypothesis_english),
        "punctuation_accuracy": _token_accuracy(reference_punctuation, hypothesis_punctuation),
        "heading_f1": _f1(reference_headings, hypothesis_headings),
        "paragraph_boundary_f1": _f1(reference_boundaries, hypothesis_boundaries),
        "reading_order_accuracy": _reading_order_accuracy(
            ground_truth.blocks, hypothesis.blocks, matches
        ),
        "table_row_preservation": table_row_preservation,
        "table_cell_preservation": table_cell_preservation,
        "missing_block_count": len(ground_truth.blocks) - len(matches),
        "hallucinated_block_count": len(hypothesis.blocks) - len(matches),
        "hallucinated_text_rate": _safe_rate(
            max(0, len(hypothesis_text) - len(reference_text)), len(hypothesis_text)
        ),
        "unresolved_text_rate": _safe_rate(
            sum(len(block.literal_text) for block in hypothesis.blocks if block.unresolved),
            len(hypothesis_text),
        ),
    }
