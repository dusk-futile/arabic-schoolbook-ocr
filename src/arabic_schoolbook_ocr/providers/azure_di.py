from __future__ import annotations

import io
import time
from collections.abc import Sequence
from typing import Any

from PIL.Image import Image

from ..config import Settings
from ..privacy import require_cloud_consent
from ..schemas import (
    ApiUsage,
    BlockType,
    BoundingBox,
    OcrBlock,
    OcrLine,
    OcrPageResult,
    PageContext,
    TableCell,
    TableData,
)
from .errors import ProviderUnavailableError


def _bbox_from_polygon(polygon: Sequence[Any] | None, width: int, height: int) -> BoundingBox:
    if not polygon:
        return BoundingBox(x=0, y=0, width=width, height=height)
    coordinates: list[tuple[float, float]] = []
    for point in polygon:
        if hasattr(point, "x") and hasattr(point, "y"):
            coordinates.append((float(point.x), float(point.y)))
        elif isinstance(point, Sequence) and len(point) >= 2:
            coordinates.append((float(point[0]), float(point[1])))
    if not coordinates:
        return BoundingBox(x=0, y=0, width=width, height=height)
    x1, x2 = min(x for x, _ in coordinates), max(x for x, _ in coordinates)
    y1, y2 = min(y for _, y in coordinates), max(y for _, y in coordinates)
    return BoundingBox(x=x1, y=y1, width=max(0, x2 - x1), height=max(0, y2 - y1))


def _span_confidence(spans: Sequence[Any] | None, words: Sequence[Any] | None) -> float:
    if not words or not spans:
        return 0.0
    confidences: list[float] = []
    for word in words:
        word_span = getattr(word, "span", None)
        if word_span is None:
            continue
        for span in spans:
            if word_span.offset >= span.offset and (
                word_span.offset + word_span.length <= span.offset + span.length
            ):
                confidences.append(float(getattr(word, "confidence", 0.0) or 0.0))
                break
    return sum(confidences) / len(confidences) if confidences else 0.0


def _line_confidence(line: Any, words: Sequence[Any] | None) -> float:
    return _span_confidence(getattr(line, "spans", None), words)


class AzureDocumentIntelligenceProvider:
    name = "azure-document-intelligence"

    def __init__(self, settings: Settings, *, max_attempts: int = 3) -> None:
        self.settings = settings
        self.max_attempts = max_attempts
        self._client: Any | None = None

    def _load_client(self) -> Any:
        if self._client is not None:
            return self._client
        endpoint = self.settings.azure_document_intelligence_endpoint
        key = self.settings.azure_document_intelligence_key
        if not endpoint or key is None:
            raise ProviderUnavailableError(
                "Azure endpoint and key must be configured before selecting Cloud Accurate mode"
            )
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise ProviderUnavailableError("Install the azure optional dependency") from exc
        self._client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key.get_secret_value()),
            logging_enable=False,
            retry_total=max(0, self.max_attempts - 1),
        )
        return self._client

    def process_page(self, page_image: Image, context: PageContext) -> OcrPageResult:
        # Consent is checked before the image is serialized.
        require_cloud_consent("azure", context)
        started = time.perf_counter()
        buffer = io.BytesIO()
        page_image.convert("RGB").save(buffer, format="PNG")
        payload = buffer.getvalue()
        last_error: Exception | None = None
        result: Any | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                poller = self._load_client().begin_analyze_document(
                    "prebuilt-layout",
                    body=io.BytesIO(payload),
                    content_type="image/png",
                    logging_enable=False,
                )
                result = poller.result()
                break
            except Exception as exc:  # Azure exceptions are optional-import types.
                last_error = exc
                if attempt == self.max_attempts:
                    raise
                time.sleep(min(2 ** (attempt - 1), 4))
        if result is None:
            raise RuntimeError("Azure returned no result") from last_error

        width, height = page_image.size
        page = result.pages[0] if result.pages else None
        words = list(getattr(page, "words", None) or [])
        blocks: list[OcrBlock] = []
        paragraph_spans: set[tuple[int, int]] = set()
        for paragraph in getattr(result, "paragraphs", None) or []:
            regions = list(getattr(paragraph, "bounding_regions", None) or [])
            if not regions:
                continue
            bbox = _bbox_from_polygon(regions[0].polygon, width, height)
            role = str(getattr(paragraph, "role", "") or "").lower()
            block_type = {
                "title": BlockType.DOCUMENT_TITLE,
                "sectionheading": BlockType.HEADING_1,
                "pageheader": BlockType.HEADER,
                "pagefooter": BlockType.FOOTER,
                "pagenumber": BlockType.PAGE_NUMBER,
            }.get(role, BlockType.BODY_PARAGRAPH)
            spans = list(getattr(paragraph, "spans", None) or [])
            confidence = _span_confidence(spans, words)
            line = OcrLine(text=paragraph.content, bbox=bbox, confidence=confidence)
            for span in spans:
                paragraph_spans.add((span.offset, span.length))
            blocks.append(
                OcrBlock(
                    block_type=block_type,
                    bbox=bbox,
                    lines=[line],
                    confidence=confidence,
                )
            )

        if not blocks and page is not None:
            for line in getattr(page, "lines", None) or []:
                confidence = _line_confidence(line, words)
                bbox = _bbox_from_polygon(line.polygon, width, height)
                blocks.append(
                    OcrBlock(
                        block_type=BlockType.UNKNOWN,
                        bbox=bbox,
                        lines=[OcrLine(text=line.content, bbox=bbox, confidence=confidence)],
                        confidence=confidence,
                    )
                )

        for table in getattr(result, "tables", None) or []:
            regions = list(getattr(table, "bounding_regions", None) or [])
            bbox = _bbox_from_polygon(regions[0].polygon if regions else None, width, height)
            cells: list[TableCell] = []
            for cell in table.cells:
                cell_regions = list(getattr(cell, "bounding_regions", None) or [])
                cells.append(
                    TableCell(
                        row=cell.row_index,
                        column=cell.column_index,
                        row_span=getattr(cell, "row_span", 1) or 1,
                        column_span=getattr(cell, "column_span", 1) or 1,
                        text=cell.content,
                        bbox=_bbox_from_polygon(
                            cell_regions[0].polygon if cell_regions else None, width, height
                        ),
                    )
                )
            blocks.append(
                OcrBlock(
                    block_type=BlockType.TABLE,
                    bbox=bbox,
                    lines=[],
                    confidence=0.0,
                    table=TableData(
                        rows=table.row_count,
                        columns=table.column_count,
                        cells=cells,
                    ),
                )
            )

        price = self.settings.azure_document_intelligence_price_per_1000_pages
        usage = ApiUsage(
            provider=self.name,
            api_calls=1,
            pages_billed=1,
            estimated_cost=None if price is None else price / 1000,
        )
        raw = result.as_dict() if hasattr(result, "as_dict") else {}
        return OcrPageResult(
            provider=self.name,
            page_number=context.page_number,
            width=width,
            height=height,
            blocks=blocks,
            raw=raw,
            warnings=[]
            if price is not None
            else ["Azure price not configured; cost is unestimated"],
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage=usage,
        )
