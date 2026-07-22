from arabic_schoolbook_ocr.pipeline import apply_layout
from arabic_schoolbook_ocr.schemas import (
    BlockType,
    BoundingBox,
    LayoutRegion,
    LayoutResult,
    OcrBlock,
    OcrLine,
    OcrPageResult,
)


def _line(text: str, x: float, y: float) -> OcrLine:
    return OcrLine(
        text=text,
        bbox=BoundingBox(x=x, y=y, width=120, height=40),
        confidence=0.9,
    )


def _ocr(lines: list[OcrLine]) -> OcrPageResult:
    return OcrPageResult(
        provider="fixture",
        page_number=1,
        width=1000,
        height=1400,
        blocks=[
            OcrBlock(
                bbox=BoundingBox(x=0, y=0, width=1000, height=1400),
                lines=lines,
                confidence=0.9,
            )
        ],
    )


def test_overlapping_parent_does_not_duplicate_child_lines() -> None:
    lines = [_line("الأول", 700, 80), _line("الثاني", 700, 300)]
    layout = LayoutResult(
        provider="fixture",
        width=1000,
        height=1400,
        regions=[
            LayoutRegion(
                block_type=BlockType.BODY_PARAGRAPH,
                bbox=BoundingBox(x=100, y=20, width=800, height=450),
                raw_label="text",
            ),
            LayoutRegion(
                block_type=BlockType.QUESTION,
                bbox=BoundingBox(x=650, y=50, width=250, height=120),
                raw_label="text",
            ),
            LayoutRegion(
                block_type=BlockType.QUESTION,
                bbox=BoundingBox(x=650, y=270, width=250, height=120),
                raw_label="text",
            ),
        ],
    )

    blocks = apply_layout(_ocr(lines), layout)

    assert len(blocks) == 2
    assert [block.lines[0].text for block in blocks] == ["الأول", "الثاني"]


def test_detected_table_gets_real_cell_structure() -> None:
    lines = [
        _line("الفصل", 760, 100),
        _line("الموضوع", 420, 100),
        _line("الصفحة", 80, 100),
        _line("الأول", 760, 250),
        _line("مقدمة", 420, 250),
        _line("٤", 80, 250),
    ]
    layout = LayoutResult(
        provider="fixture",
        width=1000,
        height=1400,
        regions=[
            LayoutRegion(
                block_type=BlockType.TABLE,
                bbox=BoundingBox(x=20, y=40, width=920, height=400),
                raw_label="table",
            )
        ],
    )

    blocks = apply_layout(_ocr(lines), layout)

    assert len(blocks) == 1
    assert blocks[0].table is not None
    assert blocks[0].table.rows == 2
    assert blocks[0].table.columns == 3
    assert blocks[0].table.cells[0].text == "الفصل"
