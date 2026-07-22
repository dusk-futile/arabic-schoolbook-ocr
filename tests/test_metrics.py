import pytest

from arabic_schoolbook_ocr.metrics import calculate_page_metrics
from arabic_schoolbook_ocr.schemas import (
    BlockType,
    BoundingBox,
    CanonicalBlock,
    CanonicalPage,
    TableCell,
    TableData,
)


def page(text: str) -> CanonicalPage:
    return CanonicalPage(
        page_number=1,
        width=100,
        height=100,
        source_image="source.png",
        blocks=[
            CanonicalBlock(
                block_type=BlockType.BODY_PARAGRAPH,
                bbox=BoundingBox(x=0, y=0, width=100, height=100),
                reading_order=0,
                literal_text=text,
                unicode_normalized_text=text,
                approved_corrected_text=text,
            )
        ],
    )


def test_metrics_refuse_unreviewed_ground_truth() -> None:
    with pytest.raises(ValueError):
        calculate_page_metrics(page("نص"), page("نص"), human_reviewed=False)


def test_exact_match_has_zero_error() -> None:
    metrics = calculate_page_metrics(
        page("نص 25 Chapter"), page("نص 25 Chapter"), human_reviewed=True
    )
    assert metrics["cer"] == 0
    assert metrics["wer"] == 0
    assert metrics["digit_accuracy"] == 1
    assert metrics["english_token_accuracy"] == 1
    assert metrics["reading_order_accuracy"] == 1


def test_metrics_match_blocks_by_geometry_and_compare_table_text() -> None:
    ground_truth = page("عنوان")
    ground_truth.blocks[0].block_type = BlockType.TABLE
    ground_truth.blocks[0].table = TableData(
        rows=1,
        columns=2,
        cells=[
            TableCell(row=0, column=0, text="عنوان"),
            TableCell(row=0, column=1, text="25"),
        ],
    )
    hypothesis = page("عنوان")
    hypothesis.blocks[0].block_type = BlockType.TABLE
    hypothesis.blocks[0].table = TableData(
        rows=1,
        columns=2,
        cells=[
            TableCell(row=0, column=0, text="عنوان"),
            TableCell(row=0, column=1, text="25"),
        ],
    )

    metrics = calculate_page_metrics(ground_truth, hypothesis, human_reviewed=True)

    assert ground_truth.blocks[0].id != hypothesis.blocks[0].id
    assert metrics["reading_order_accuracy"] == 1
    assert metrics["table_row_preservation"] == 1
    assert metrics["table_cell_preservation"] == 1
    assert metrics["missing_block_count"] == 0
    assert metrics["hallucinated_block_count"] == 0
