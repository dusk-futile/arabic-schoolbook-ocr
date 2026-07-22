from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image as PILImage
from PIL.Image import Image

from .adjudicators import DisabledAdjudicator
from .boundaries import reconstruct_lines
from .gemini_agents import (
    GeminiDocumentFormattingAnalyst,
    GeminiVerificationPolicy,
    apply_formatting_analysis,
    protected_content_reasons,
)
from .persistence import JobStore
from .preprocessing import PreprocessConfig, preprocess_page, recrop_high_resolution
from .protocols import LayoutProvider, OcrProvider, VisualAdjudicator
from .reading_order import reading_order_rtl
from .schemas import (
    AdjudicationContext,
    BlockType,
    BoundaryDecision,
    BoundingBox,
    CanonicalBlock,
    CanonicalDocument,
    CanonicalPage,
    Direction,
    LayoutResult,
    OcrBlock,
    OcrCandidate,
    OcrLine,
    OcrPageResult,
    PageContext,
    PageStatus,
)
from .tables import infer_table_data
from .text_runs import normalize_unicode, segment_mixed_runs


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _center_inside(line_bbox: BoundingBox, region_bbox: BoundingBox) -> bool:
    center_x = line_bbox.x + line_bbox.width / 2
    center_y = line_bbox.y + line_bbox.height / 2
    return (
        region_bbox.x <= center_x <= region_bbox.right
        and region_bbox.y <= center_y <= region_bbox.bottom
    )


def _intersection_over_union(first: BoundingBox, second: BoundingBox) -> float:
    overlap_width = max(0.0, min(first.right, second.right) - max(first.x, second.x))
    overlap_height = max(0.0, min(first.bottom, second.bottom) - max(first.y, second.y))
    intersection = overlap_width * overlap_height
    union = first.width * first.height + second.width * second.height - intersection
    return intersection / union if union > 0 else 0.0


def _match_by_geometry(
    block: CanonicalBlock,
    candidates: list[CanonicalBlock],
    used_ids: set[str],
) -> CanonicalBlock | None:
    available = [candidate for candidate in candidates if candidate.id not in used_ids]
    if not available:
        return None
    scored = [
        (
            _intersection_over_union(block.bbox, candidate.bbox)
            + (0.05 if block.block_type == candidate.block_type else 0.0),
            candidate,
        )
        for candidate in available
    ]
    score, candidate = max(scored, key=lambda item: item[0])
    return candidate if score >= 0.2 else None


def apply_layout(ocr: OcrPageResult, layout: LayoutResult) -> list[OcrBlock]:
    """Assign OCR lines to layout regions while retaining every unassigned line."""

    if (
        len(layout.regions) == 1
        and layout.regions[0].raw_label in {"full-page-fallback", "fallback-full-page"}
        and any(block.block_type != BlockType.UNKNOWN for block in ocr.blocks)
    ):
        return ocr.blocks

    all_lines = [line for block in ocr.blocks for line in block.lines]
    result: list[OcrBlock] = []
    assigned_ids: set[str] = set()
    assignments: dict[str, list[OcrLine]] = {region.id: [] for region in layout.regions}
    for line in all_lines:
        candidates = [region for region in layout.regions if _center_inside(line.bbox, region.bbox)]
        if candidates:
            smallest = min(candidates, key=lambda region: region.bbox.width * region.bbox.height)
            assignments[smallest.id].append(line)
            assigned_ids.add(line.id)
    for region in layout.regions:
        lines = assignments[region.id]
        if not lines and region.block_type not in {
            BlockType.FIGURE,
            BlockType.DECORATIVE_REGION,
            BlockType.EQUATION_IMAGE,
        }:
            continue
        confidence_values = [line.confidence for line in lines]
        table = (
            infer_table_data(lines, region.bbox) if region.block_type == BlockType.TABLE else None
        )
        result.append(
            OcrBlock(
                block_type=region.block_type,
                bbox=region.bbox,
                lines=lines,
                confidence=(
                    sum(confidence_values) / len(confidence_values)
                    if confidence_values
                    else region.confidence
                ),
                table=table,
                provider_metadata={"layout_label": region.raw_label},
            )
        )
    for block in ocr.blocks:
        if block.table is not None:
            result.append(block)
    for line in all_lines:
        if line.id not in assigned_ids:
            result.append(
                OcrBlock(
                    block_type=BlockType.UNKNOWN,
                    bbox=line.bbox,
                    lines=[line],
                    confidence=line.confidence,
                    provider_metadata={"layout_label": "unassigned"},
                )
            )
    return result or ocr.blocks


def _refine_block_type(block: OcrBlock, text: str) -> BlockType:
    stripped = text.strip()
    if block.block_type in {BlockType.UNKNOWN, BlockType.BODY_PARAGRAPH}:
        if stripped.startswith(("س:", "سؤال", "؟")) or stripped.endswith("؟"):
            return BlockType.QUESTION
        if stripped.startswith(("- ", "• ", "● ", "▪ ", "◦ ", "* ")):
            return BlockType.BULLET_LIST
        if len(stripped) <= 260 and re.match(r"^\s*[0-9\u0660-\u0669]+(?:\s*[-.):]|\s+)", stripped):
            return BlockType.QUESTION
    if block.block_type != BlockType.UNKNOWN:
        return block.block_type
    if len(stripped) <= 80 and block.confidence >= 0.7 and len(block.lines) == 1:
        # This is deliberately conservative: uncertain short regions remain UNKNOWN.
        return BlockType.HEADING_3
    return BlockType.UNKNOWN


def canonicalize_blocks(blocks: list[OcrBlock], page_width: int) -> list[CanonicalBlock]:
    ordered = reading_order_rtl(blocks, page_width)
    canonical: list[CanonicalBlock] = []
    for index, block in enumerate(ordered):
        if block.table is not None:
            literal = "\n".join(
                "\t".join(
                    next(
                        (
                            cell.text
                            for cell in block.table.cells
                            if cell.row == row and cell.column == column
                        ),
                        "",
                    )
                    for column in range(block.table.columns)
                )
                for row in range(block.table.rows)
            )
            decisions: list[BoundaryDecision] = []
        else:
            literal, decisions = reconstruct_lines(block.lines, block.block_type)
        block_type = _refine_block_type(block, literal)
        normalized = normalize_unicode(literal)
        canonical.append(
            CanonicalBlock(
                id=block.id,
                block_type=block_type,
                bbox=block.bbox,
                reading_order=index,
                literal_text=literal,
                unicode_normalized_text=normalized,
                confidence=block.confidence,
                paragraph_direction=Direction.RTL,
                runs=segment_mixed_runs(literal),
                line_ids=[line.id for line in block.lines],
                boundaries=decisions,
                table=block.table,
                unresolved=block.confidence < 0.7 or block_type == BlockType.UNKNOWN,
                evidence={"provider_metadata": block.provider_metadata},
            )
        )
    return canonical


class PagePipeline:
    def __init__(
        self,
        *,
        primary: OcrProvider,
        layout: LayoutProvider,
        store: JobStore,
        verifier: OcrProvider | None = None,
        adjudicator: VisualAdjudicator | None = None,
        preprocess_config: PreprocessConfig | None = None,
        adjudication_threshold: float = 0.72,
        verification_policy: GeminiVerificationPolicy | None = None,
        formatting_analyst: GeminiDocumentFormattingAnalyst | None = None,
        automatic_correction_confidence_threshold: float = 0.95,
    ) -> None:
        self.primary = primary
        self.layout = layout
        self.verifier = verifier
        self.adjudicator = adjudicator or DisabledAdjudicator()
        self.store = store
        self.preprocess_config = preprocess_config or PreprocessConfig()
        self.adjudication_threshold = adjudication_threshold
        self.verification_policy = verification_policy
        self.formatting_analyst = formatting_analyst
        self.automatic_correction_confidence_threshold = automatic_correction_confidence_threshold

    def process_page(self, source: Image, context: PageContext) -> CanonicalPage:
        page_dir = self.store.page_dir(context.page_number)
        timings: dict[str, int] = {}
        started = time.perf_counter()
        try:
            source_path = page_dir / "source.png"
            source.convert("RGB").save(source_path, format="PNG")

            stage = time.perf_counter()
            preprocessed = preprocess_page(source, self.preprocess_config)
            preprocessed_path = page_dir / "preprocessed.png"
            preprocessed.save(preprocessed_path, format="PNG")
            timings["preprocess"] = round((time.perf_counter() - stage) * 1000)

            stage = time.perf_counter()
            layout = self.layout.analyze_page(preprocessed)
            timings["layout"] = round((time.perf_counter() - stage) * 1000)
            self.store.save_json(f"pages/{context.page_number:04d}/layout.json", layout)

            stage = time.perf_counter()
            primary_result = self.primary.process_page(preprocessed, context)
            timings["primary_ocr"] = round((time.perf_counter() - stage) * 1000)
            self.store.save_json(f"pages/{context.page_number:04d}/ocr.json", primary_result)
            blocks = apply_layout(primary_result, layout)
            canonical = canonicalize_blocks(blocks, source.width)

            verifier_result: OcrPageResult | None = None
            verifier_blocks: list[CanonicalBlock] = []
            if self.verifier is not None:
                stage = time.perf_counter()
                verifier_result = self.verifier.process_page(preprocessed, context)
                timings["verifier_ocr"] = round((time.perf_counter() - stage) * 1000)
                self.store.save_json(
                    f"pages/{context.page_number:04d}/verifier.json", verifier_result
                )
                verifier_blocks = canonicalize_blocks(
                    apply_layout(verifier_result, layout), source.width
                )

            adjudication_ms = 0
            adjudication_usage = []
            adjudication_warnings: list[str] = []
            matched_verifier_ids: set[str] = set()
            for block in canonical:
                crop: Image | None = None
                verifier_block = _match_by_geometry(block, verifier_blocks, matched_verifier_ids)
                if verifier_block is not None:
                    matched_verifier_ids.add(verifier_block.id)
                disagreement = (
                    verifier_block is not None
                    and normalize_unicode(verifier_block.literal_text)
                    != block.unicode_normalized_text
                )
                trigger_reasons = (
                    self.verification_policy.reasons(block, verifier_block)
                    if self.verification_policy is not None
                    else ["provider-disagreement" if disagreement else "low-confidence"]
                    if block.confidence < self.adjudication_threshold or disagreement
                    else []
                )
                if block.block_type in {BlockType.FIGURE, BlockType.EQUATION_IMAGE}:
                    crop = recrop_high_resolution(source, block.bbox)
                    crop_dir = page_dir / "figure_crops"
                    crop_dir.mkdir(parents=True, exist_ok=True)
                    crop_path = crop_dir / f"{block.id}.png"
                    crop.save(crop_path, format="PNG")
                    block.source_crop = str(crop_path.relative_to(self.store.path))
                if not trigger_reasons:
                    continue
                candidates = [
                    OcrCandidate(
                        text=block.literal_text,
                        confidence=block.confidence,
                        provider=primary_result.provider,
                    )
                ]
                if verifier_block is not None:
                    candidates.append(
                        OcrCandidate(
                            text=verifier_block.literal_text,
                            confidence=verifier_block.confidence,
                            provider=verifier_result.provider if verifier_result else "verifier",
                        )
                    )
                if crop is None:
                    crop = recrop_high_resolution(source, block.bbox)
                    crop_dir = page_dir / "disagreement_crops"
                    crop_dir.mkdir(parents=True, exist_ok=True)
                    crop_path = crop_dir / f"{block.id}.png"
                    crop.save(crop_path, format="PNG")
                    block.source_crop = str(crop_path.relative_to(self.store.path))
                stage = time.perf_counter()
                try:
                    protected_reasons = protected_content_reasons(
                        block.literal_text, block.block_type
                    )
                    decision = self.adjudicator.adjudicate(
                        crop,
                        candidates,
                        AdjudicationContext(
                            page=context,
                            block_id=block.id,
                            reason=",".join(trigger_reasons),
                            crop_bbox=block.bbox,
                            full_page_crop=False,
                            region_type=block.block_type,
                            languages=[
                                "ar",
                                *(["en"] if re.search(r"[A-Za-z]", block.literal_text) else []),
                            ],
                            protected_content=protected_reasons,
                        ),
                    )
                except Exception as exc:
                    adjudication_ms += round((time.perf_counter() - stage) * 1000)
                    block.evidence["adjudication_error"] = {
                        "type": type(exc).__name__,
                        "message": str(exc)[:300],
                    }
                    block.unresolved = True
                    adjudication_warnings.append(
                        f"Adjudication failed for block {block.id}; primary text retained"
                    )
                    continue
                adjudication_ms += round((time.perf_counter() - stage) * 1000)
                block.evidence["candidates"] = [
                    candidate.model_dump(mode="json") for candidate in candidates
                ]
                block.evidence["adjudication"] = decision.model_dump(mode="json")
                if decision.usage is not None:
                    adjudication_usage.append(decision.usage)
                selected_changed = (
                    decision.selected_text is not None
                    and decision.selected_text != block.literal_text
                )
                protected_reasons = protected_content_reasons(
                    decision.selected_text or block.literal_text, block.block_type
                )
                if decision.provider == "gemini-visual-verifier":
                    evidence_sufficient = (
                        not decision.unresolved
                        and decision.selected_text is not None
                        and decision.confidence >= self.automatic_correction_confidence_threshold
                    )
                    if selected_changed and evidence_sufficient and not protected_reasons:
                        block.approved_corrected_text = decision.selected_text
                        block.evidence["automatic_correction"] = {
                            "reason": "Gemini crop-level visual verification",
                            "confidence": decision.confidence,
                            "source_crop": block.source_crop,
                            "visual_evidence": decision.visual_evidence,
                            "protected_content": [],
                            "automatic": True,
                        }
                        block.unresolved = False
                    else:
                        block.unresolved = not evidence_sufficient or bool(protected_reasons)
                    block.evidence["protected_content"] = protected_reasons
                else:
                    # Non-Gemini adjudicators remain evidence-only adapters.
                    block.unresolved = decision.unresolved or selected_changed
            timings["adjudication"] = adjudication_ms
            page_warnings = layout.warnings + primary_result.warnings + adjudication_warnings
            verifier_only_count = sum(
                bool(block.literal_text.strip()) and block.id not in matched_verifier_ids
                for block in verifier_blocks
            )
            if verifier_only_count:
                page_warnings.append(
                    f"Verifier detected {verifier_only_count} additional block(s); "
                    "human review required"
                )
            usage = [
                item
                for item in [
                    primary_result.usage,
                    verifier_result.usage if verifier_result else None,
                ]
                if item
            ] + adjudication_usage
            page = CanonicalPage(
                page_number=context.page_number,
                width=source.width,
                height=source.height,
                source_image=str(source_path.relative_to(self.store.path)),
                preprocessed_image=str(preprocessed_path.relative_to(self.store.path)),
                blocks=canonical,
                warnings=page_warnings,
                timings_ms=timings,
                usage=usage,
            )
            formatting_ms = 0
            if self.formatting_analyst is not None:
                stage = time.perf_counter()
                try:
                    formatting_response = self.formatting_analyst.analyze(source, page, context)
                    apply_formatting_analysis(page, formatting_response.result)
                    page.usage.append(formatting_response.usage)
                    self.store.save_json(
                        f"pages/{context.page_number:04d}/formatting_analysis.json",
                        formatting_response.result,
                    )
                except Exception as exc:
                    page.warnings.append(
                        "Formatting analysis failed; deterministic local structure retained "
                        f"({type(exc).__name__})"
                    )
                formatting_ms = round((time.perf_counter() - stage) * 1000)
            timings["formatting"] = formatting_ms
            timings["total"] = round((time.perf_counter() - started) * 1000)
            page.timings_ms = timings
            self.store.save_json(f"pages/{context.page_number:04d}/canonical.json", page)
            return page
        except Exception as exc:
            timings["total"] = round((time.perf_counter() - started) * 1000)
            error = f"{type(exc).__name__}: {exc}"
            failed = CanonicalPage(
                page_number=context.page_number,
                width=source.width,
                height=source.height,
                source_image=str((page_dir / "source.png").relative_to(self.store.path)),
                status=PageStatus.FAILED,
                error=error,
                timings_ms=timings,
            )
            self.store.save_json(
                f"pages/{context.page_number:04d}/error.json",
                {"page": context.page_number, "error": error, "timings_ms": timings},
            )
            return failed


def process_images(
    *,
    image_paths: Iterable[Path],
    document: CanonicalDocument,
    pipeline: PagePipeline,
    context_factory: Callable[[int, int], PageContext],
) -> CanonicalDocument:
    paths = list(image_paths)
    pipeline.store.initialize()
    pipeline.store.save_json(
        "run_manifest.json",
        {
            "job_id": pipeline.store.job_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "page_count": len(paths),
            "training_approved": False,
            "providers": {
                "primary": pipeline.primary.name,
                "layout": pipeline.layout.name,
                "verifier": pipeline.verifier.name if pipeline.verifier else None,
                "adjudicator": pipeline.adjudicator.name,
            },
        },
    )
    for page_number, path in enumerate(paths, start=1):
        with PILImage.open(path) as opened:
            page = pipeline.process_page(opened.copy(), context_factory(page_number, len(paths)))
        document.pages = [
            existing for existing in document.pages if existing.page_number != page_number
        ]
        document.pages.append(page)
        document.pages.sort(key=lambda item: item.page_number)
        document.updated_at = datetime.now(timezone.utc)
        pipeline.store.save_json("document/canonical_document.json", document)
    return document
