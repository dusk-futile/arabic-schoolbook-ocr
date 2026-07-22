from pathlib import Path

from PIL import Image

from arabic_schoolbook_ocr.adjudicators import DisabledAdjudicator
from arabic_schoolbook_ocr.persistence import JobStore
from arabic_schoolbook_ocr.pipeline import PagePipeline
from arabic_schoolbook_ocr.providers import FullPageLayoutProvider, MockOcrProvider
from arabic_schoolbook_ocr.schemas import (
    AdjudicationResult,
    ApiUsage,
    BlockType,
    BoundingBox,
    LayoutRegion,
    LayoutResult,
    PageContext,
    PageStatus,
)


class UsageAdjudicator:
    name = "usage-adjudicator"

    def adjudicate(self, crop, candidates, context):
        return AdjudicationResult(
            provider=self.name,
            selected_text=candidates[0].text,
            confidence=0.9,
            unresolved=False,
            usage=ApiUsage(provider=self.name, api_calls=1, estimated_cost=0.01),
        )


class FailingAdjudicator:
    name = "failing-adjudicator"

    def adjudicate(self, crop, candidates, context):
        raise RuntimeError("synthetic adjudicator outage")


class GeminiEvidenceAdjudicator:
    name = "gemini-visual-verifier"

    def __init__(self, selected_text: str) -> None:
        self.selected_text = selected_text

    def adjudicate(self, crop, candidates, context):
        return AdjudicationResult(
            provider=self.name,
            selected_text=self.selected_text,
            confidence=0.99,
            unresolved=False,
            decision="NEW_TRANSCRIPTION",
            visual_evidence="Visible glyph-by-glyph match",
            content_changed=True,
        )


class FigureLayoutProvider:
    name = "figure-layout"

    def analyze_page(self, page_image: Image.Image) -> LayoutResult:
        width, height = page_image.size
        return LayoutResult(
            provider=self.name,
            width=width,
            height=height,
            regions=[
                LayoutRegion(
                    block_type=BlockType.BODY_PARAGRAPH,
                    bbox=BoundingBox(x=0, y=0, width=width, height=height * 0.5),
                    confidence=0.95,
                ),
                LayoutRegion(
                    block_type=BlockType.FIGURE,
                    bbox=BoundingBox(
                        x=width * 0.1,
                        y=height * 0.6,
                        width=width * 0.8,
                        height=height * 0.3,
                    ),
                    confidence=0.95,
                ),
            ],
        )


def test_failed_page_is_checkpointed_without_raising(tmp_path: Path) -> None:
    store = JobStore(tmp_path, "test-job")
    store.initialize()
    pipeline = PagePipeline(
        primary=MockOcrProvider(fail_pages={2}),
        layout=FullPageLayoutProvider(),
        adjudicator=DisabledAdjudicator(),
        store=store,
    )
    image = Image.new("RGB", (1000, 1400), "white")
    page = pipeline.process_page(
        image,
        PageContext(
            job_id="test-job",
            page_number=2,
            total_pages=5,
            source_sha256="0" * 64,
        ),
    )
    assert page.status == PageStatus.FAILED
    assert (store.page_dir(2) / "error.json").is_file()


def test_high_confidence_figure_is_saved_for_docx_embedding(tmp_path: Path) -> None:
    store = JobStore(tmp_path, "figure-job")
    store.initialize()
    pipeline = PagePipeline(
        primary=MockOcrProvider(lines=["نص أعلى الشكل"]),
        layout=FigureLayoutProvider(),
        adjudicator=DisabledAdjudicator(),
        store=store,
    )
    page = pipeline.process_page(
        Image.new("RGB", (1000, 1400), "white"),
        PageContext(
            job_id="figure-job",
            page_number=1,
            total_pages=1,
            source_sha256="0" * 64,
        ),
    )
    figure = next(block for block in page.blocks if block.block_type == BlockType.FIGURE)
    assert figure.source_crop is not None
    assert (store.path / figure.source_crop).is_file()


def test_adjudicator_usage_is_recorded_on_page(tmp_path: Path) -> None:
    store = JobStore(tmp_path, "usage-job")
    store.initialize()
    pipeline = PagePipeline(
        primary=MockOcrProvider(lines=["نص"]),
        layout=FullPageLayoutProvider(),
        adjudicator=UsageAdjudicator(),
        adjudication_threshold=1.0,
        store=store,
    )
    page = pipeline.process_page(
        Image.new("RGB", (600, 800), "white"),
        PageContext(
            job_id="usage-job",
            page_number=1,
            total_pages=1,
            source_sha256="0" * 64,
        ),
    )
    assert sum(usage.api_calls for usage in page.usage) == 1
    assert sum(usage.estimated_cost or 0 for usage in page.usage) == 0.01


def test_adjudicator_failure_retains_primary_page(tmp_path: Path) -> None:
    store = JobStore(tmp_path, "adjudicator-failure-job")
    store.initialize()
    pipeline = PagePipeline(
        primary=MockOcrProvider(lines=["نص محفوظ"]),
        layout=FullPageLayoutProvider(),
        adjudicator=FailingAdjudicator(),
        adjudication_threshold=1.0,
        store=store,
    )
    page = pipeline.process_page(
        Image.new("RGB", (600, 800), "white"),
        PageContext(
            job_id="adjudicator-failure-job",
            page_number=1,
            total_pages=1,
            source_sha256="0" * 64,
        ),
    )
    assert page.status == PageStatus.COMPLETED
    assert page.blocks[0].literal_text == "نص محفوظ"
    assert page.blocks[0].unresolved is True
    assert "primary text retained" in page.warnings[-1]


def test_high_confidence_unprotected_gemini_change_is_reportable_polished_text(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path, "gemini-correction-job")
    store.initialize()
    pipeline = PagePipeline(
        primary=MockOcrProvider(lines=["نص خام"]),
        layout=FullPageLayoutProvider(),
        adjudicator=GeminiEvidenceAdjudicator("نص مرئي"),
        adjudication_threshold=1.0,
        store=store,
    )
    page = pipeline.process_page(
        Image.new("RGB", (600, 800), "white"),
        PageContext(
            job_id="gemini-correction-job",
            page_number=1,
            total_pages=1,
            source_sha256="0" * 64,
        ),
    )

    block = page.blocks[0]
    assert block.literal_text == "نص خام"
    assert block.approved_corrected_text == "نص مرئي"
    assert block.unresolved is False
    assert block.evidence["automatic_correction"]["source_crop"] == block.source_crop


def test_protected_digit_change_remains_human_reviewable(tmp_path: Path) -> None:
    store = JobStore(tmp_path, "gemini-protected-job")
    store.initialize()
    pipeline = PagePipeline(
        primary=MockOcrProvider(lines=["الدرجة 25"]),
        layout=FullPageLayoutProvider(),
        adjudicator=GeminiEvidenceAdjudicator("الدرجة ٢٥"),
        adjudication_threshold=1.0,
        store=store,
    )
    page = pipeline.process_page(
        Image.new("RGB", (600, 800), "white"),
        PageContext(
            job_id="gemini-protected-job",
            page_number=1,
            total_pages=1,
            source_sha256="0" * 64,
        ),
    )

    block = page.blocks[0]
    assert block.approved_corrected_text is None
    assert block.unresolved is True
    assert "numbers or dates" in block.evidence["protected_content"]
