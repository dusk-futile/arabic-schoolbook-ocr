from __future__ import annotations

from collections.abc import Sequence

from PIL.Image import Image

from ..schemas import (
    BlockType,
    BoundingBox,
    LayoutRegion,
    LayoutResult,
    OcrBlock,
    OcrLine,
    OcrPageResult,
    PageContext,
)


class MockOcrProvider:
    name = "mock"

    def __init__(self, lines: Sequence[str] | None = None, *, fail_pages: set[int] | None = None):
        self.lines = list(lines or ["نص عربي تجريبي", "افتح Chapter 3 ثم أجب."])
        self.fail_pages = fail_pages or set()

    def process_page(self, page_image: Image, context: PageContext) -> OcrPageResult:
        if context.page_number in self.fail_pages:
            raise RuntimeError(f"Synthetic provider failure on page {context.page_number}")
        width, height = page_image.size
        line_height = max(24, height // max(len(self.lines) + 2, 3))
        lines = [
            OcrLine(
                text=text,
                bbox=BoundingBox(
                    x=width * 0.1,
                    y=line_height * (index + 1),
                    width=width * 0.8,
                    height=line_height * 0.7,
                ),
                confidence=0.91,
            )
            for index, text in enumerate(self.lines)
        ]
        block = OcrBlock(
            block_type=BlockType.BODY_PARAGRAPH,
            bbox=BoundingBox(
                x=width * 0.1, y=line_height, width=width * 0.8, height=line_height * len(lines)
            ),
            lines=lines,
            confidence=0.91,
        )
        return OcrPageResult(
            provider=self.name,
            page_number=context.page_number,
            width=width,
            height=height,
            blocks=[block],
        )


class MockLayoutProvider:
    name = "mock-layout"

    def analyze_page(self, page_image: Image) -> LayoutResult:
        width, height = page_image.size
        return LayoutResult(
            provider=self.name,
            width=width,
            height=height,
            regions=[
                LayoutRegion(
                    block_type=BlockType.BODY_PARAGRAPH,
                    bbox=BoundingBox(
                        x=width * 0.08, y=height * 0.08, width=width * 0.84, height=height * 0.84
                    ),
                    confidence=0.9,
                    raw_label="text",
                )
            ],
        )


class FullPageLayoutProvider:
    """Fallback layout that preserves OCR-provider block semantics when available."""

    name = "full-page-layout-fallback"

    def analyze_page(self, page_image: Image) -> LayoutResult:
        width, height = page_image.size
        return LayoutResult(
            provider=self.name,
            width=width,
            height=height,
            regions=[
                LayoutRegion(
                    block_type=BlockType.UNKNOWN,
                    bbox=BoundingBox(x=0, y=0, width=width, height=height),
                    confidence=0,
                    raw_label="full-page-fallback",
                )
            ],
            warnings=["No independent layout parser was configured"],
        )
