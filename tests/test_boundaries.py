from arabic_schoolbook_ocr.boundaries import decide_boundary, reconstruct_lines
from arabic_schoolbook_ocr.schemas import (
    BlockType,
    BoundaryType,
    BoundingBox,
    OcrLine,
)


def line(text: str, y: float, *, right: float = 900) -> OcrLine:
    return OcrLine(
        text=text,
        bbox=BoundingBox(x=right - 600, y=y, width=600, height=40),
        confidence=0.9,
    )


def test_default_visual_wrap_becomes_space() -> None:
    first, second = line("هذه جملة", 100), line("مستمرة هنا.", 150)
    decision = decide_boundary(first, second, BlockType.BODY_PARAGRAPH)
    text, _ = reconstruct_lines([first, second], BlockType.BODY_PARAGRAPH)
    assert decision.boundary == BoundaryType.CONTINUE_WITH_SPACE
    assert text == "هذه جملة مستمرة هنا."


def test_list_marker_creates_item_boundary() -> None:
    decision = decide_boundary(line("• الأول", 100), line("• الثاني", 160), BlockType.BULLET_LIST)
    assert decision.boundary == BoundaryType.LIST_ITEM_BOUNDARY
