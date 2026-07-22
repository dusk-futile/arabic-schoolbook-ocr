from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise

from .schemas import (
    BlockType,
    BoundaryDecision,
    BoundaryType,
    OcrLine,
)

_LIST_PATTERN = re.compile(r"^\s*(?:[\-•●▪◦*]|\(?[0-9\u0660-\u0669]+[.)\-]|[أ-ي][.)\-])\s+")
_TERMINAL_PATTERN = re.compile(r"[.!?؟؛:]\s*$")


def decide_boundary(before: OcrLine, after: OcrLine, block_type: BlockType) -> BoundaryDecision:
    height = max(before.bbox.height, after.bbox.height, 1)
    gap = max(0.0, after.bbox.y - before.bbox.bottom)
    normalized_gap = gap / height
    indent_delta = abs(before.bbox.right - after.bbox.right) / max(before.bbox.width, 1)
    reasons: list[str] = []

    if block_type == BlockType.TABLE:
        boundary = BoundaryType.TABLE_CELL_BOUNDARY
        confidence = 0.98
        reasons.append("table block")
    elif _LIST_PATTERN.match(after.text):
        boundary = BoundaryType.LIST_ITEM_BOUNDARY
        confidence = 0.96
        reasons.append("next line begins with a list marker")
    elif normalized_gap >= 1.8:
        boundary = BoundaryType.BLANK_PARAGRAPH_SPACE
        confidence = min(0.98, 0.75 + normalized_gap / 10)
        reasons.append(f"vertical gap {normalized_gap:.2f} line-heights")
    elif normalized_gap >= 0.9 and (indent_delta >= 0.08 or _TERMINAL_PATTERN.search(before.text)):
        boundary = BoundaryType.NEW_PARAGRAPH
        confidence = 0.88
        reasons.append(f"vertical gap {normalized_gap:.2f} and paragraph cue")
    elif before.text.endswith(("-", "ـ")) and normalized_gap < 0.55:
        boundary = BoundaryType.CONTINUE_WITHOUT_SPACE
        confidence = 0.8
        reasons.append("line ends with a visible continuation glyph")
    elif (
        block_type in {BlockType.CAPTION, BlockType.QUESTION, BlockType.ANSWER_OPTION}
        and normalized_gap > 0.65
    ):
        boundary = BoundaryType.SOFT_LINE_BREAK
        confidence = 0.78
        reasons.append("semantic block retains an intentional line break")
    else:
        boundary = BoundaryType.CONTINUE_WITH_SPACE
        confidence = 0.76
        reasons.append("same paragraph geometry")
    return BoundaryDecision(
        before_line_id=before.id,
        after_line_id=after.id,
        boundary=boundary,
        confidence=confidence,
        reasons=reasons,
    )


def reconstruct_lines(
    lines: Sequence[OcrLine], block_type: BlockType
) -> tuple[str, list[BoundaryDecision]]:
    if not lines:
        return "", []
    ordered = sorted(lines, key=lambda line: (line.bbox.y, -line.bbox.x))
    decisions = [decide_boundary(before, after, block_type) for before, after in pairwise(ordered)]
    text = ordered[0].text
    separators = {
        BoundaryType.CONTINUE_WITH_SPACE: " ",
        BoundaryType.CONTINUE_WITHOUT_SPACE: "",
        BoundaryType.SOFT_LINE_BREAK: "\n",
        BoundaryType.NEW_PARAGRAPH: "\n\n",
        BoundaryType.BLANK_PARAGRAPH_SPACE: "\n\n",
        BoundaryType.LIST_ITEM_BOUNDARY: "\n",
        BoundaryType.TABLE_CELL_BOUNDARY: "\t",
        BoundaryType.PAGE_BREAK: "\f",
        BoundaryType.SECTION_BREAK: "\n\n",
    }
    for decision, line in zip(decisions, ordered[1:], strict=True):
        text += separators[decision.boundary] + line.text
    return text, decisions
