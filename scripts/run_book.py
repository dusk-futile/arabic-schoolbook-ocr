from __future__ import annotations

import argparse
import json
import platform
import random
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from arabic_schoolbook_ocr.adjudicators import DisabledAdjudicator, GeminiAdjudicator
from arabic_schoolbook_ocr.config import Settings
from arabic_schoolbook_ocr.ground_truth import DEFAULT_BENCHMARK_PAGES
from arabic_schoolbook_ocr.pdf_render import pdf_page_count, render_pdf_pages
from arabic_schoolbook_ocr.persistence import JobStore, atomic_write_json
from arabic_schoolbook_ocr.pipeline import PagePipeline, sha256_file
from arabic_schoolbook_ocr.preprocessing import recrop_high_resolution
from arabic_schoolbook_ocr.providers import (
    AzureDocumentIntelligenceProvider,
    FullPageLayoutProvider,
    MockLayoutProvider,
    MockOcrProvider,
    PaddleLocalLayoutProvider,
    PaddleLocalOcrProvider,
    WindowsOcrProvider,
)
from arabic_schoolbook_ocr.rendering import (
    DocxDocumentRenderer,
    DocxPdfExportError,
    export_docx_to_pdf,
)
from arabic_schoolbook_ocr.reporting import (
    write_correction_reports,
    write_pending_accuracy_report,
    write_review_report,
)
from arabic_schoolbook_ocr.schemas import (
    BlockType,
    CanonicalDocument,
    CanonicalPage,
    CloudConsent,
    LayoutResult,
    PageContext,
    PageStatus,
)
from arabic_schoolbook_ocr.visualization import (
    draw_layout_overlay,
    draw_reading_order_overlay,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run a checkpointed full-book OCR acceptance job")
    result.add_argument("pdf", type=Path)
    result.add_argument(
        "--mode", choices=["windows", "local", "azure", "hybrid", "mock"], default="local"
    )
    result.add_argument("--job-root", type=Path, default=ROOT / "jobs")
    result.add_argument("--job-id")
    result.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    result.add_argument("--verifier", choices=["windows", "paddle", "none"], default="none")
    result.add_argument("--cloud-opt-in", action="store_true")
    result.add_argument("--full-book-confirmed", action="store_true")
    result.add_argument("--resume", action="store_true")
    result.add_argument("--retry-failed", action="store_true")
    return result


def _package_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for package in ("paddlepaddle", "paddleocr", "paddlex", "numpy"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "not-installed"
    return result


def _providers(arguments: argparse.Namespace, settings: Settings):
    def windows() -> WindowsOcrProvider:
        return WindowsOcrProvider(ROOT / "scripts" / "run_windows_ocr.ps1")

    if arguments.mode == "windows":
        return windows(), FullPageLayoutProvider(), None, DisabledAdjudicator()
    if arguments.mode == "mock":
        return MockOcrProvider(), MockLayoutProvider(), None, DisabledAdjudicator()
    if arguments.mode == "local":
        verifier = (
            windows()
            if arguments.verifier == "windows"
            else PaddleLocalOcrProvider(device=arguments.device)
            if arguments.verifier == "paddle"
            else None
        )
        return (
            PaddleLocalOcrProvider(device=arguments.device),
            PaddleLocalLayoutProvider(device=arguments.device),
            verifier,
            DisabledAdjudicator(),
        )
    if arguments.mode == "azure":
        return (
            AzureDocumentIntelligenceProvider(settings),
            FullPageLayoutProvider(),
            None,
            DisabledAdjudicator(),
        )
    verifier = (
        PaddleLocalOcrProvider(device=arguments.device)
        if arguments.verifier == "paddle"
        else windows()
        if arguments.verifier == "windows"
        else None
    )
    return (
        AzureDocumentIntelligenceProvider(settings),
        FullPageLayoutProvider(),
        verifier,
        GeminiAdjudicator(settings),
    )


def _save_overlays(store: JobStore, page: CanonicalPage) -> None:
    page_dir = store.page_dir(page.page_number)
    source_path = page_dir / "source.png"
    if not source_path.is_file():
        return
    layout_path = page_dir / "layout.json"
    layout = (
        LayoutResult.model_validate_json(layout_path.read_text(encoding="utf-8"))
        if layout_path.is_file()
        else None
    )
    with Image.open(source_path) as source:
        if layout is not None:
            draw_layout_overlay(source, layout.regions).save(page_dir / "layout_overlay.png")
        draw_reading_order_overlay(source, page.blocks).save(page_dir / "reading_order_overlay.png")


def _manifest(
    *,
    job_id: str,
    pdf: Path,
    source_sha256: str,
    total_pages: int,
    arguments: argparse.Namespace,
    primary: Any,
    layout: Any,
    verifier: Any,
    adjudicator: Any,
    consent: CloudConsent,
    started_at: str,
    status: str,
    completed_pages: int,
    failed_pages: list[int],
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "started_at": started_at,
        "updated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "source_filename": pdf.name,
        "source_sha256": source_sha256,
        "classification": "EVALUATION_ONLY",
        "training_approved": False,
        "total_source_pages": total_pages,
        "completed_pages": completed_pages,
        "failed_pages": failed_pages,
        "mode": arguments.mode,
        "device": arguments.device,
        "providers": {
            "primary": primary.name,
            "layout": layout.name,
            "verifier": verifier.name if verifier else None,
            "adjudicator": adjudicator.name,
        },
        "package_versions": _package_versions(),
        "model_revisions": {
            "PP-DocLayout_plus-L": "aa52b8528c84f9b1a34ac3a88fe0e576edb9d11d",
            "PP-OCRv3_mobile_det": "58f4e5b132e34e516486fb0d0266c662feb48ca1",
            "arabic_PP-OCRv3_mobile_rec": "2feba5ee71822bb7ee0bbecf134e62f8ec9f368a",
        },
        "cloud_consent": consent.model_dump(mode="json"),
        "full_document_gemini": False,
        "host": {"platform": platform.platform(), "python": platform.python_version()},
    }


def _review_queue(document: CanonicalDocument, source_sha256: str) -> dict[str, list[int]]:
    failed = [page.page_number for page in document.pages if page.status == PageStatus.FAILED]
    low_confidence = sorted(
        {
            page.page_number
            for page in document.pages
            if any(block.unresolved or block.confidence < 0.7 for block in page.blocks)
        }
    )
    english = sorted(
        {
            page.page_number
            for page in document.pages
            if any(any("A" <= char <= "z" for char in block.literal_text) for block in page.blocks)
        }
    )
    tables = sorted(
        {
            page.page_number
            for page in document.pages
            if any(block.table is not None for block in page.blocks)
        }
    )
    rng = random.Random(int(source_sha256[:16], 16))
    random_twenty = sorted(rng.sample(range(1, len(document.pages) + 1), k=20))
    return {
        "failed_pages": failed,
        "low_confidence_pages": low_confidence,
        "english_containing_pages": english,
        "table_pages": tables,
        "deterministic_random_twenty": random_twenty,
    }


def _ensure_visual_crops(document: CanonicalDocument, store: JobStore) -> None:
    changed = False
    for page in document.pages:
        missing = [
            block
            for block in page.blocks
            if block.block_type in {BlockType.FIGURE, BlockType.EQUATION_IMAGE}
            and not block.source_crop
        ]
        if not missing:
            continue
        source_path = store.path / page.source_image
        if not source_path.is_file():
            page.warnings.append("Figure crop could not be created because source image is missing")
            continue
        with Image.open(source_path) as source:
            for block in missing:
                crop_dir = store.page_dir(page.page_number) / "figure_crops"
                crop_dir.mkdir(parents=True, exist_ok=True)
                crop_path = crop_dir / f"{block.id}.png"
                recrop_high_resolution(source, block.bbox).save(crop_path, format="PNG")
                block.source_crop = str(crop_path.relative_to(store.path))
                changed = True
        store.save_json(f"pages/{page.page_number:04d}/canonical.json", page)
    if changed:
        document.updated_at = datetime.now(UTC)
        store.save_json("document/canonical_document.json", document)


def _write_summary(
    path: Path,
    *,
    document: CanonicalDocument,
    elapsed_seconds: float,
    unresolved_count: int,
    review_queue: dict[str, list[int]],
    rendered_pdf_status: str,
    total_source_pages: int,
) -> None:
    failed = [page.page_number for page in document.pages if page.status == PageStatus.FAILED]
    path.write_text(
        "# Full-book acceptance summary\n\n"
        f"- Source pages accounted for: {len(document.pages)}/{total_source_pages}\n"
        f"- Completed pages: {document.completed_pages}\n"
        f"- Failed pages: {failed or 'none'}\n"
        f"- Unresolved blocks: {unresolved_count}\n"
        f"- Processing time: {elapsed_seconds:.1f} seconds\n"
        "- Accuracy: `UNMEASURED_PENDING_HUMAN_GROUND_TRUTH`\n"
        "- Cloud API usage: none for Local mode; see run manifest for other modes\n"
        f"- Rendered PDF: {rendered_pdf_status}\n\n"
        "The 30-page benchmark remains EVALUATION_ONLY and is not training data. "
        "No accuracy percentage may be reported until a human reviewer corrects and "
        "approves every selected page. The review queue is stored in "
        "`review_queue.json`; draft selection categories require visual confirmation.\n\n"
        f"Review queues: `{json.dumps(review_queue, ensure_ascii=False)}`\n",
        encoding="utf-8",
    )


def main() -> None:
    arguments = parser().parse_args()
    if not arguments.full_book_confirmed:
        raise SystemExit("Full-book processing requires --full-book-confirmed")
    if arguments.mode in {"azure", "hybrid"} and not arguments.cloud_opt_in:
        raise SystemExit("Cloud modes require the explicit --cloud-opt-in flag")
    if arguments.verifier == "windows" and platform.system() != "Windows":
        raise SystemExit("The Windows verifier is only available on Windows")

    settings = Settings()
    settings.assert_training_disabled()
    pdf = arguments.pdf.resolve()
    if not pdf.is_file():
        raise SystemExit(f"PDF not found: {pdf}")
    total_pages = pdf_page_count(pdf)
    source_sha256 = sha256_file(pdf)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    job_id = arguments.job_id or f"book-{arguments.mode}-{timestamp}"
    store = JobStore(arguments.job_root, job_id)
    store.initialize()
    canonical_path = store.path / "document" / "canonical_document.json"
    if canonical_path.is_file():
        if not arguments.resume:
            raise SystemExit(f"Job exists; pass --resume to continue: {store.path}")
        document = CanonicalDocument.model_validate_json(canonical_path.read_text(encoding="utf-8"))
        if document.source_sha256 != source_sha256:
            raise SystemExit("Resume refused because the source PDF hash changed")
    else:
        document = CanonicalDocument(
            title=pdf.stem,
            source_filename=pdf.name,
            source_sha256=source_sha256,
            classification="EVALUATION_ONLY",
            run_configuration={
                "mode": arguments.mode,
                "pages": list(range(1, total_pages + 1)),
                "dpi": 300,
                "training_approved": False,
                "cloud_opt_in": arguments.cloud_opt_in,
                "full_document_gemini": False,
            },
        )

    primary, layout, verifier, adjudicator = _providers(arguments, settings)
    pipeline = PagePipeline(
        primary=primary,
        layout=layout,
        verifier=verifier,
        adjudicator=adjudicator,
        store=store,
    )
    consent = CloudConsent(
        cloud_opt_in=arguments.cloud_opt_in,
        allowed_providers={"azure", "gemini"}
        if arguments.mode == "hybrid"
        else {"azure"}
        if arguments.mode == "azure"
        else set(),
        allowed_pages=set(range(1, total_pages + 1)) if arguments.cloud_opt_in else None,
        allow_full_document_gemini=False,
        acknowledged_at=datetime.now(UTC) if arguments.cloud_opt_in else None,
    )
    started_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()

    existing = {page.page_number: page for page in document.pages}
    try:
        for page_number in range(1, total_pages + 1):
            if page_number in existing and not (
                arguments.retry_failed and existing[page_number].status == PageStatus.FAILED
            ):
                continue
            try:
                image_path = render_pdf_pages(
                    pdf,
                    store.path / "source" / "rendered",
                    [page_number],
                    dpi=300,
                )[0]
                with Image.open(image_path) as source:
                    page = pipeline.process_page(
                        source.copy(),
                        PageContext(
                            job_id=job_id,
                            page_number=page_number,
                            total_pages=total_pages,
                            source_sha256=source_sha256,
                            consent=consent,
                        ),
                    )
            except Exception as exc:
                page_dir = store.page_dir(page_number)
                source_path = page_dir / "source.png"
                Image.new("RGB", (1, 1), "white").save(source_path)
                page = CanonicalPage(
                    page_number=page_number,
                    width=1,
                    height=1,
                    source_image=str(source_path.relative_to(store.path)),
                    status=PageStatus.FAILED,
                    error=f"{type(exc).__name__}: {exc}",
                )
                store.save_json(
                    f"pages/{page_number:04d}/error.json",
                    {"page": page_number, "error": page.error},
                )
            _save_overlays(store, page)
            document.pages = [item for item in document.pages if item.page_number != page_number]
            document.pages.append(page)
            document.pages.sort(key=lambda item: item.page_number)
            document.updated_at = datetime.now(UTC)
            store.save_json("document/canonical_document.json", document)
            failed = [
                item.page_number for item in document.pages if item.status == PageStatus.FAILED
            ]
            store.save_json(
                "run_manifest.json",
                _manifest(
                    job_id=job_id,
                    pdf=pdf,
                    source_sha256=source_sha256,
                    total_pages=total_pages,
                    arguments=arguments,
                    primary=primary,
                    layout=layout,
                    verifier=verifier,
                    adjudicator=adjudicator,
                    consent=consent,
                    started_at=started_at,
                    status="RUNNING",
                    completed_pages=document.completed_pages,
                    failed_pages=failed,
                ),
            )
            print(
                json.dumps(
                    {
                        "page": page_number,
                        "total": total_pages,
                        "status": page.status.value,
                        "elapsed_seconds": round(time.perf_counter() - started, 1),
                    }
                ),
                flush=True,
            )
    except KeyboardInterrupt:
        print("Interrupted; the last completed page checkpoint is preserved.", file=sys.stderr)
        raise SystemExit(130) from None

    _ensure_visual_crops(document, store)
    unresolved = [
        {
            "page": page.page_number,
            "block_id": block.id,
            "block_type": block.block_type.value,
            "confidence": block.confidence,
            "source_crop": block.source_crop,
        }
        for page in document.pages
        for block in page.blocks
        if block.unresolved
    ]
    output = store.path / "output"
    store.save_json(
        "output/issue_report.json",
        {
            "accuracy_status": "UNMEASURED_PENDING_HUMAN_GROUND_TRUTH",
            "failed_pages": [
                page.page_number for page in document.pages if page.status == PageStatus.FAILED
            ],
            "unresolved": unresolved,
        },
    )
    store.save_json("output/canonical_document.json", document)
    review_queue = _review_queue(document, source_sha256)
    store.save_json("output/review_queue.json", review_queue)
    store.save_json(
        "output/visual_inspection_status.json",
        {
            "status": "PENDING_HUMAN_INSPECTION",
            "completed": False,
            "required_queues": review_queue,
            "note": (
                "Generation of a queue is not visual approval. Every failed, low-confidence, "
                "English-containing, and table page plus the random sample must be checked."
            ),
        },
    )

    renderer = DocxDocumentRenderer()
    literal = renderer.render_docx(document, output / "book_literal.docx")
    renderer.render_docx(document, output / "book_polished.docx", polished=True)
    write_correction_reports(document, output)
    write_review_report(document, store.path, output / "review_report.html")
    write_pending_accuracy_report(
        output / "accuracy_report.html",
        benchmark_pages=[page for page, _ in DEFAULT_BENCHMARK_PAGES],
        modes=[
            "Windows baseline",
            "Local Paddle pipeline",
            "Azure Document Intelligence",
            "Gemini direct extraction",
            "Hybrid Azure + local verification",
            "Hybrid Azure + Gemini adjudication",
            "Final reconstructed DOCX",
        ],
    )

    rendered_pdf_status = "not attempted"
    rendered_pdf_page_count: int | None = None
    try:
        rendered_pdf = export_docx_to_pdf(literal.output_path, output / "book_rendered.pdf")
        rendered_pdf_page_count = pdf_page_count(rendered_pdf)
        rendered_pdf_status = (
            f"created locally: {rendered_pdf.name}; pages={rendered_pdf_page_count}; "
            f"source_pages={total_pages}"
        )
        validation_pages = sorted(
            set(review_queue["deterministic_random_twenty"])
            | {page for page, _ in DEFAULT_BENCHMARK_PAGES}
        )
        render_pdf_pages(
            rendered_pdf,
            output / "rendered_docx_pages",
            validation_pages,
            dpi=150,
        )
    except (DocxPdfExportError, OSError) as exc:
        rendered_pdf_status = f"unavailable: {exc}"
    atomic_write_json(
        output / "book_rendered.status.json",
        {
            "status": rendered_pdf_status,
            "page_count": rendered_pdf_page_count,
            "source_page_count": total_pages,
            "page_count_matches_source": rendered_pdf_page_count == total_pages,
            "cloud_converter_used": False,
        },
    )

    elapsed = time.perf_counter() - started
    _write_summary(
        output / "summary.md",
        document=document,
        elapsed_seconds=elapsed,
        unresolved_count=len(unresolved),
        review_queue=review_queue,
        rendered_pdf_status=rendered_pdf_status,
        total_source_pages=total_pages,
    )
    failed_pages = [page.page_number for page in document.pages if page.status == PageStatus.FAILED]
    manifest = _manifest(
        job_id=job_id,
        pdf=pdf,
        source_sha256=source_sha256,
        total_pages=total_pages,
        arguments=arguments,
        primary=primary,
        layout=layout,
        verifier=verifier,
        adjudicator=adjudicator,
        consent=consent,
        started_at=started_at,
        status="COMPLETED" if len(document.pages) == total_pages else "INCOMPLETE",
        completed_pages=document.completed_pages,
        failed_pages=failed_pages,
    )
    manifest.update(
        {
            "finished_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "unresolved_blocks": len(unresolved),
            "rendered_pdf_status": rendered_pdf_status,
            "rendered_pdf_page_count": rendered_pdf_page_count,
            "rendered_pdf_page_count_matches_source": rendered_pdf_page_count == total_pages,
        }
    )
    store.save_json("run_manifest.json", manifest)
    store.save_json("output/run_manifest.json", manifest)
    print(
        json.dumps(
            {
                "job": str(store.path),
                "source_pages": total_pages,
                "accounted_pages": len(document.pages),
                "completed_pages": document.completed_pages,
                "failed_pages": failed_pages,
                "unresolved_blocks": len(unresolved),
                "accuracy": "UNMEASURED_PENDING_HUMAN_GROUND_TRUTH",
                "rendered_pdf": rendered_pdf_status,
                "elapsed_seconds": round(elapsed, 1),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
