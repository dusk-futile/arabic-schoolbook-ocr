from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PIL.Image import Image

from .schemas import (
    AdjudicationContext,
    AdjudicationResult,
    CanonicalDocument,
    LayoutResult,
    OcrCandidate,
    OcrPageResult,
    PageContext,
    RenderResult,
)


class OcrProvider(Protocol):
    name: str

    def process_page(self, page_image: Image, context: PageContext) -> OcrPageResult: ...


class VisualAdjudicator(Protocol):
    name: str

    def adjudicate(
        self,
        crop: Image,
        candidates: list[OcrCandidate],
        context: AdjudicationContext,
    ) -> AdjudicationResult: ...


class LayoutProvider(Protocol):
    name: str

    def analyze_page(self, page_image: Image) -> LayoutResult: ...


class DocumentRenderer(Protocol):
    def render_docx(
        self,
        document: CanonicalDocument,
        output_path: Path,
        *,
        polished: bool = False,
    ) -> RenderResult: ...
