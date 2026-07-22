from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .persistence import atomic_write_json
from .schemas import CanonicalPage


class GroundTruthPage(BaseModel):
    page_number: int = Field(ge=1)
    category: str
    source_image: str
    draft: CanonicalPage | None = None
    reviewed_page: CanonicalPage | None = None
    human_reviewed: bool = False
    reviewer: str | None = None
    reviewed_at: datetime | None = None

    def approve(self, reviewed_page: CanonicalPage, reviewer: str) -> None:
        self.reviewed_page = reviewed_page
        self.human_reviewed = True
        self.reviewer = reviewer
        self.reviewed_at = datetime.now(timezone.utc)


class GroundTruthManifest(BaseModel):
    source_sha256: str
    classification: str = "EVALUATION_ONLY"
    training_allowed: bool = False
    pages: list[GroundTruthPage]

    def assert_ready_for_metrics(self) -> None:
        incomplete = [page.page_number for page in self.pages if not page.human_reviewed]
        if incomplete:
            raise ValueError(f"Human correction is incomplete for pages: {incomplete}")


DEFAULT_BENCHMARK_PAGES: list[tuple[int, str]] = [
    (4, "normal-text"),
    (7, "heading"),
    (12, "normal-text"),
    (18, "questions"),
    (25, "lists"),
    (31, "normal-text"),
    (36, "heading"),
    (42, "western-digits"),
    (48, "arabic-indic-digits"),
    (53, "mixed-arabic-english"),
    (60, "normal-text"),
    (67, "colored-box"),
    (74, "questions"),
    (81, "answer-choices"),
    (88, "one-column"),
    (95, "two-column"),
    (102, "lists"),
    (109, "heading"),
    (116, "mixed-arabic-english"),
    (123, "normal-text"),
    (130, "western-digits"),
    (137, "arabic-indic-digits"),
    (144, "colored-box"),
    (151, "questions"),
    (158, "answer-choices"),
    (165, "two-column"),
    (172, "table-candidate"),
    (184, "difficult"),
    (197, "difficult"),
    (209, "table-or-toc"),
]


def create_manifest(
    source_sha256: str,
    image_root: Path,
    output_path: Path,
    selections: list[tuple[int, str]] | None = None,
) -> GroundTruthManifest:
    manifest = GroundTruthManifest(
        source_sha256=source_sha256,
        pages=[
            GroundTruthPage(
                page_number=page_number,
                category=category,
                source_image=str(image_root / f"page-{page_number:04d}.png"),
            )
            for page_number, category in (selections or DEFAULT_BENCHMARK_PAGES)
        ],
    )
    atomic_write_json(output_path, manifest)
    return manifest
