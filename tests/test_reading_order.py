from arabic_schoolbook_ocr.reading_order import reading_order_rtl
from arabic_schoolbook_ocr.schemas import BlockType, BoundingBox, OcrBlock, OcrLine


def block(label: str, x: int, y: int, *, width: int = 350) -> OcrBlock:
    bbox = BoundingBox(x=x, y=y, width=width, height=100)
    return OcrBlock(
        block_type=BlockType.BODY_PARAGRAPH,
        bbox=bbox,
        lines=[OcrLine(text=label, bbox=bbox, confidence=0.9)],
        confidence=0.9,
        provider_metadata={"label": label},
    )


def test_two_columns_are_read_right_then_left() -> None:
    blocks = [
        block("left-2", 100, 300),
        block("right-1", 550, 100),
        block("left-1", 100, 100),
        block("right-2", 550, 300),
    ]
    ordered = reading_order_rtl(blocks, 1000)
    assert [item.provider_metadata["label"] for item in ordered] == [
        "right-1",
        "right-2",
        "left-1",
        "left-2",
    ]


def test_centered_heading_precedes_lower_right_aligned_subheading() -> None:
    heading = block("chapter-title", 325, 100)
    subheading = block("introduction", 780, 260, width=120)

    ordered = reading_order_rtl([subheading, heading], 1000)

    assert [item.provider_metadata["label"] for item in ordered] == [
        "chapter-title",
        "introduction",
    ]
