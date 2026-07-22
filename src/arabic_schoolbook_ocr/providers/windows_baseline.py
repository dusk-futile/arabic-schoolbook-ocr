from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from PIL.Image import Image

from ..schemas import (
    BlockType,
    BoundingBox,
    OcrBlock,
    OcrLine,
    OcrPageResult,
    PageContext,
)
from .errors import ProviderResponseError, ProviderUnavailableError


class WindowsOcrProvider:
    """Reproducible Windows.Media.Ocr baseline; Windows-only and confidence-free."""

    name = "windows-media-ocr"

    def __init__(self, script_path: Path, *, language_tag: str = "ar-SA") -> None:
        self.script_path = script_path.resolve()
        self.language_tag = language_tag
        if not self.script_path.is_file():
            raise ProviderUnavailableError(f"Windows OCR script not found: {self.script_path}")

    def process_page(self, page_image: Image, context: PageContext) -> OcrPageResult:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="arabic-ocr-windows-") as temporary:
            temporary_path = Path(temporary)
            input_path = temporary_path / "page.png"
            output_path = temporary_path / "result.json"
            page_image.convert("RGB").save(input_path, format="PNG")
            try:
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(self.script_path),
                        "-InputPath",
                        str(input_path),
                        "-OutputPath",
                        str(output_path),
                        "-LanguageTag",
                        self.language_tag,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (FileNotFoundError, subprocess.SubprocessError) as exc:
                raise ProviderUnavailableError(f"Windows OCR invocation failed: {exc}") from exc
            payload = json.loads(output_path.read_text(encoding="utf-8-sig"))
        records = payload.get("records", [])
        if len(records) != 1:
            raise ProviderResponseError("Windows OCR did not return exactly one page record")
        record = records[0]
        width, height = page_image.size
        lines: list[OcrLine] = []
        for line_data in record.get("lines", []):
            rectangles = [word.get("bounding_rect", []) for word in line_data.get("words", [])]
            rectangles = [rect for rect in rectangles if len(rect) == 4]
            if rectangles:
                x1 = min(float(rect[0]) for rect in rectangles)
                y1 = min(float(rect[1]) for rect in rectangles)
                x2 = max(float(rect[0]) + float(rect[2]) for rect in rectangles)
                y2 = max(float(rect[1]) + float(rect[3]) for rect in rectangles)
                bbox = BoundingBox(x=x1, y=y1, width=x2 - x1, height=y2 - y1)
            else:
                bbox = BoundingBox(x=0, y=0, width=width, height=height)
            lines.append(
                OcrLine(
                    text=str(line_data.get("text", "")),
                    bbox=bbox,
                    confidence=0.5,
                    provider_metadata={"confidence_available": False},
                )
            )
        if not lines:
            raise ProviderResponseError("Windows OCR returned no lines")
        x1 = min(line.bbox.x for line in lines)
        y1 = min(line.bbox.y for line in lines)
        x2 = max(line.bbox.right for line in lines)
        y2 = max(line.bbox.bottom for line in lines)
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
                    confidence=0.5,
                    provider_metadata={"confidence_available": False},
                )
            ],
            raw=payload,
            warnings=["Windows.Media.Ocr does not provide confidence scores"],
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
