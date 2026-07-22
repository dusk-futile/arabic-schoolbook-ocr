from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BlockType(str, Enum):
    DOCUMENT_TITLE = "DOCUMENT_TITLE"
    CHAPTER_TITLE = "CHAPTER_TITLE"
    HEADING_1 = "HEADING_1"
    HEADING_2 = "HEADING_2"
    HEADING_3 = "HEADING_3"
    BODY_PARAGRAPH = "BODY_PARAGRAPH"
    QUESTION = "QUESTION"
    ANSWER_OPTION = "ANSWER_OPTION"
    BULLET_LIST = "BULLET_LIST"
    NUMBERED_LIST = "NUMBERED_LIST"
    DEFINITION_BOX = "DEFINITION_BOX"
    EXAMPLE_BOX = "EXAMPLE_BOX"
    NOTE_BOX = "NOTE_BOX"
    TABLE = "TABLE"
    FIGURE = "FIGURE"
    CAPTION = "CAPTION"
    EQUATION_IMAGE = "EQUATION_IMAGE"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    PAGE_NUMBER = "PAGE_NUMBER"
    DECORATIVE_REGION = "DECORATIVE_REGION"
    UNKNOWN = "UNKNOWN"


class BoundaryType(str, Enum):
    CONTINUE_WITH_SPACE = "CONTINUE_WITH_SPACE"
    CONTINUE_WITHOUT_SPACE = "CONTINUE_WITHOUT_SPACE"
    SOFT_LINE_BREAK = "SOFT_LINE_BREAK"
    NEW_PARAGRAPH = "NEW_PARAGRAPH"
    BLANK_PARAGRAPH_SPACE = "BLANK_PARAGRAPH_SPACE"
    LIST_ITEM_BOUNDARY = "LIST_ITEM_BOUNDARY"
    TABLE_CELL_BOUNDARY = "TABLE_CELL_BOUNDARY"
    PAGE_BREAK = "PAGE_BREAK"
    SECTION_BREAK = "SECTION_BREAK"


class Direction(str, Enum):
    RTL = "RTL"
    LTR = "LTR"
    NEUTRAL = "NEUTRAL"


class TextAlignment(str, Enum):
    RIGHT = "RIGHT"
    LEFT = "LEFT"
    CENTER = "CENTER"
    JUSTIFY = "JUSTIFY"


class FontSizeClass(str, Enum):
    SMALL = "SMALL"
    NORMAL = "NORMAL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"
    EXTRA_LARGE = "EXTRA_LARGE"


class Script(str, Enum):
    ARABIC = "ARABIC"
    LATIN = "LATIN"
    DIGIT = "DIGIT"
    NEUTRAL = "NEUTRAL"


class BoundingBox(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(ge=0)
    height: float = Field(ge=0)
    coordinate_space: Literal["pixel", "normalized"] = "pixel"

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


class TextRun(BaseModel):
    text: str
    script: Script
    direction: Direction


class OcrCandidate(BaseModel):
    text: str
    confidence: float = Field(ge=0, le=1)
    provider: str


class OcrLine(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    bbox: BoundingBox
    confidence: float = Field(default=0, ge=0, le=1)
    polygon: list[float] = Field(default_factory=list)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class TableCell(BaseModel):
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    text: str
    bbox: BoundingBox | None = None


class TableData(BaseModel):
    rows: int = Field(ge=1)
    columns: int = Field(ge=1)
    cells: list[TableCell] = Field(default_factory=list)


class OcrBlock(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    block_type: BlockType = BlockType.UNKNOWN
    bbox: BoundingBox
    lines: list[OcrLine] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    table: TableData | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class ApiUsage(BaseModel):
    provider: str
    api_calls: int = Field(default=0, ge=0)
    pages_billed: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)
    currency: str = "USD"


class OcrPageResult(BaseModel):
    provider: str
    page_number: int = Field(ge=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    blocks: list[OcrBlock] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)
    usage: ApiUsage | None = None


class LayoutRegion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    block_type: BlockType = BlockType.UNKNOWN
    bbox: BoundingBox
    confidence: float = Field(default=0, ge=0, le=1)
    raw_label: str | None = None


class LayoutResult(BaseModel):
    provider: str
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    regions: list[LayoutRegion] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CloudConsent(BaseModel):
    cloud_opt_in: bool = False
    allowed_providers: set[str] = Field(default_factory=set)
    allowed_pages: set[int] | None = None
    allow_full_document_gemini: bool = False
    acknowledged_at: datetime | None = None

    @model_validator(mode="after")
    def consent_has_timestamp(self) -> CloudConsent:
        if self.cloud_opt_in and self.acknowledged_at is None:
            raise ValueError("Cloud opt-in requires acknowledged_at")
        return self


class PageContext(BaseModel):
    job_id: str
    page_number: int = Field(ge=1)
    total_pages: int = Field(ge=1)
    source_sha256: str
    language: str = "ar"
    consent: CloudConsent = Field(default_factory=CloudConsent)


class AdjudicationContext(BaseModel):
    page: PageContext
    block_id: str
    reason: str
    crop_bbox: BoundingBox
    full_page_crop: bool = False
    region_type: BlockType = BlockType.UNKNOWN
    languages: list[str] = Field(default_factory=lambda: ["ar"])
    protected_content: list[str] = Field(default_factory=list)


class AdjudicationResult(BaseModel):
    provider: str
    selected_text: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    rationale: str = ""
    unresolved: bool = True
    decision: str | None = None
    uncertain_spans: list[dict[str, Any]] = Field(default_factory=list)
    visual_evidence: str = ""
    content_changed: bool = False
    usage: ApiUsage | None = None


class BoundaryDecision(BaseModel):
    before_line_id: str
    after_line_id: str
    boundary: BoundaryType
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class BlockFormatting(BaseModel):
    alignment: TextAlignment | None = None
    bold: bool | None = None
    font_size_class: FontSizeClass | None = None
    space_before_pt: float | None = Field(default=None, ge=0, le=144)
    space_after_pt: float | None = Field(default=None, ge=0, le=144)
    keep_with_next: bool | None = None
    left_indent_pt: float | None = Field(default=None, ge=0, le=720)
    right_indent_pt: float | None = Field(default=None, ge=0, le=720)


class CanonicalBlock(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    block_type: BlockType
    bbox: BoundingBox
    reading_order: int = Field(ge=0)
    literal_text: str
    unicode_normalized_text: str
    approved_corrected_text: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    paragraph_direction: Direction = Direction.RTL
    paragraph_group_id: str | None = None
    runs: list[TextRun] = Field(default_factory=list)
    line_ids: list[str] = Field(default_factory=list)
    boundaries: list[BoundaryDecision] = Field(default_factory=list)
    formatting: BlockFormatting | None = None
    table: TableData | None = None
    unresolved: bool = False
    source_crop: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    def output_text(self, polished: bool) -> str:
        if polished:
            if self.approved_corrected_text is not None:
                return self.approved_corrected_text
            return self.unicode_normalized_text
        return self.literal_text


class PageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CanonicalPage(BaseModel):
    page_number: int = Field(ge=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    source_image: str
    preprocessed_image: str | None = None
    blocks: list[CanonicalBlock] = Field(default_factory=list)
    status: PageStatus = PageStatus.COMPLETED
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    timings_ms: dict[str, int] = Field(default_factory=dict)
    usage: list[ApiUsage] = Field(default_factory=list)


class CanonicalDocument(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    source_filename: str
    source_sha256: str
    classification: Literal["EVALUATION_ONLY", "TRAINING_ALLOWED", "PUBLIC_DEMO"] = (
        "EVALUATION_ONLY"
    )
    pages: list[CanonicalPage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_configuration: dict[str, Any] = Field(default_factory=dict)

    @property
    def completed_pages(self) -> int:
        return sum(page.status == PageStatus.COMPLETED for page in self.pages)


class CorrectionRecord(BaseModel):
    page: int = Field(ge=1)
    block_id: str
    source_crop: str | None = None
    literal: str
    corrected: str
    reason: str
    confidence: float = Field(ge=0, le=1)
    automatic: bool = False


class RenderResult(BaseModel):
    output_path: Path
    polished: bool
    page_count: int = Field(ge=0)
    block_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    validation_report: Path | None = None
