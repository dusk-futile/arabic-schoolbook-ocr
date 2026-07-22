from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

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
from .errors import ProviderResponseError, ProviderUnavailableError


def _safe_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    for attribute in ("json", "res"):
        candidate = getattr(value, attribute, None)
        if callable(candidate):
            candidate = candidate()
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except json.JSONDecodeError:
                continue
        if isinstance(candidate, Mapping):
            return dict(candidate)
    for method in ("to_dict", "as_dict"):
        candidate = getattr(value, method, None)
        if callable(candidate):
            result = candidate()
            if isinstance(result, Mapping):
                return dict(result)
    raise ProviderResponseError(f"Unsupported Paddle result type: {type(value)!r}")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(
            json.dumps(value, default=lambda item: getattr(item, "tolist", lambda: str(item))())
        )


def _bbox_from_xyxy(raw: Sequence[Any], *, width: int, height: int) -> BoundingBox:
    if len(raw) == 4 and all(isinstance(item, Real) for item in raw):
        x1, y1, x2, y2 = (float(item) for item in raw)
    elif len(raw) > 0 and isinstance(raw[0], Sequence):
        points = [(float(point[0]), float(point[1])) for point in raw if len(point) >= 2]
        x1, x2 = min(point[0] for point in points), max(point[0] for point in points)
        y1, y2 = min(point[1] for point in points), max(point[1] for point in points)
    else:
        return BoundingBox(x=0, y=0, width=width, height=height)
    return BoundingBox(x=max(0, x1), y=max(0, y1), width=max(0, x2 - x1), height=max(0, y2 - y1))


def _sequence_field(data: Mapping[str, Any], *names: str) -> list[Any]:
    """Return a Paddle sequence field without truth-testing NumPy arrays."""

    for name in names:
        value = data.get(name)
        if value is not None:
            return list(value)
    return []


def _compact_payload(data: Mapping[str, Any], *field_names: str) -> dict[str, Any]:
    """Keep provider evidence while excluding duplicate image tensors and feature maps."""

    return {
        field_name: _json_safe(data[field_name])
        for field_name in field_names
        if field_name in data and data[field_name] is not None
    }


_PADDLE_LABELS: dict[str, BlockType] = {
    "doc_title": BlockType.DOCUMENT_TITLE,
    "title": BlockType.HEADING_1,
    "header": BlockType.HEADER,
    "footer": BlockType.FOOTER,
    "paragraph_title": BlockType.HEADING_2,
    "section_title": BlockType.HEADING_2,
    "text": BlockType.BODY_PARAGRAPH,
    "table": BlockType.TABLE,
    "table_title": BlockType.CAPTION,
    "table_caption": BlockType.CAPTION,
    "figure": BlockType.FIGURE,
    "image": BlockType.FIGURE,
    "figure_title": BlockType.CAPTION,
    "figure_caption": BlockType.CAPTION,
    "chart": BlockType.FIGURE,
    "formula": BlockType.EQUATION_IMAGE,
    "number": BlockType.PAGE_NUMBER,
}


class PaddleLocalOcrProvider:
    """Lazy local Arabic OCR adapter suitable for CPU or a 6 GB GPU.

    Arabic currently requires Paddle's PP-OCRv3 multilingual recognizer. No model is
    downloaded until this provider is selected and `process_page` is called.
    """

    name = "paddle-local"

    def __init__(self, *, device: str = "cpu") -> None:
        self.device = device
        self._pipeline: Any | None = None

    def _load(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ProviderUnavailableError(
                "Install the local extra and PaddlePaddle before selecting Local Paddle mode"
            ) from exc
        self._pipeline = PaddleOCR(
            lang="ar",
            ocr_version="PP-OCRv3",
            device=self.device,
            enable_mkldnn=self.device != "cpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        return self._pipeline

    def process_page(self, page_image: Image, context: PageContext) -> OcrPageResult:
        started = time.perf_counter()
        try:
            import numpy as np
        except ImportError as exc:
            raise ProviderUnavailableError("Paddle local mode requires numpy") from exc
        raw_results = list(self._load().predict(np.asarray(page_image.convert("RGB"))))
        width, height = page_image.size
        lines: list[OcrLine] = []
        raw_payloads: list[dict[str, Any]] = []
        for raw_result in raw_results:
            payload = _safe_mapping(raw_result)
            data = payload.get("res", payload)
            raw_payloads.append(
                _compact_payload(
                    data,
                    "input_path",
                    "page_index",
                    "model_settings",
                    "text_det_params",
                    "text_type",
                    "rec_texts",
                    "rec_scores",
                    "rec_boxes",
                    "dt_polys",
                    "rec_polys",
                )
            )
            texts = _sequence_field(data, "rec_texts")
            scores = _sequence_field(data, "rec_scores")
            boxes = _sequence_field(data, "rec_boxes", "dt_polys")
            for index, text in enumerate(texts):
                raw_box = boxes[index] if index < len(boxes) else [0, 0, width, height]
                score = float(scores[index]) if index < len(scores) else 0.0
                lines.append(
                    OcrLine(
                        text=str(text),
                        bbox=_bbox_from_xyxy(raw_box, width=width, height=height),
                        confidence=max(0.0, min(1.0, score)),
                    )
                )
        if not lines:
            raise ProviderResponseError("Paddle returned no recognized lines")
        x1 = min(line.bbox.x for line in lines)
        y1 = min(line.bbox.y for line in lines)
        x2 = max(line.bbox.right for line in lines)
        y2 = max(line.bbox.bottom for line in lines)
        confidence = sum(line.confidence for line in lines) / len(lines)
        return OcrPageResult(
            provider=self.name,
            page_number=context.page_number,
            width=width,
            height=height,
            blocks=[
                OcrBlock(
                    block_type=BlockType.UNKNOWN,
                    bbox=BoundingBox(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    lines=lines,
                    confidence=confidence,
                )
            ],
            raw={"results": _json_safe(raw_payloads)},
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


class PaddleLocalLayoutProvider:
    name = "paddle-structure-v3"

    def __init__(self, *, device: str = "cpu", model_name: str = "PP-DocLayout_plus-L") -> None:
        self.device = device
        self.model_name = model_name
        self._pipeline: Any | None = None

    def _load(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            from paddlex import create_model
        except ImportError as exc:
            raise ProviderUnavailableError(
                "Install PaddleX and PaddlePaddle for local layout mode"
            ) from exc
        self._pipeline = create_model(
            model_name=self.model_name,
            device=self.device,
            enable_mkldnn=self.device != "cpu",
        )
        return self._pipeline

    def analyze_page(self, page_image: Image) -> LayoutResult:
        try:
            import numpy as np
        except ImportError as exc:
            raise ProviderUnavailableError("Paddle local mode requires numpy") from exc
        width, height = page_image.size
        results = list(
            self._load().predict(
                np.asarray(page_image.convert("RGB")), batch_size=1, layout_nms=True
            )
        )
        regions: list[LayoutRegion] = []
        raw_payloads: list[dict[str, Any]] = []
        for result in results:
            payload = _safe_mapping(result)
            data = payload.get("res", payload)
            raw_payloads.append(_compact_payload(data, "input_path", "page_index", "boxes"))
            for raw_region in data.get("boxes", []):
                region = _safe_mapping(raw_region)
                label = str(region.get("label", "unknown")).lower()
                raw_bbox = region.get("coordinate", region.get("bbox", [0, 0, width, height]))
                regions.append(
                    LayoutRegion(
                        block_type=_PADDLE_LABELS.get(label, BlockType.UNKNOWN),
                        bbox=_bbox_from_xyxy(raw_bbox, width=width, height=height),
                        confidence=float(region.get("score", 0.0) or 0.0),
                        raw_label=label,
                    )
                )
        if not regions:
            regions.append(
                LayoutRegion(
                    block_type=BlockType.UNKNOWN,
                    bbox=BoundingBox(x=0, y=0, width=width, height=height),
                    confidence=0,
                    raw_label="fallback-full-page",
                )
            )
        return LayoutResult(
            provider=self.name,
            width=width,
            height=height,
            regions=regions,
            raw={"results": _json_safe(raw_payloads)},
        )
