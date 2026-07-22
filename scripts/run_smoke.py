from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from arabic_schoolbook_ocr.adjudicators import DisabledAdjudicator, GeminiAdjudicator
from arabic_schoolbook_ocr.config import Settings
from arabic_schoolbook_ocr.pdf_render import pdf_page_count, render_pdf_pages
from arabic_schoolbook_ocr.persistence import JobStore
from arabic_schoolbook_ocr.pipeline import PagePipeline, sha256_file
from arabic_schoolbook_ocr.providers import (
    AzureDocumentIntelligenceProvider,
    FullPageLayoutProvider,
    MockLayoutProvider,
    MockOcrProvider,
    PaddleLocalLayoutProvider,
    PaddleLocalOcrProvider,
    WindowsOcrProvider,
)
from arabic_schoolbook_ocr.rendering import DocxDocumentRenderer
from arabic_schoolbook_ocr.reporting import write_correction_reports, write_smoke_report
from arabic_schoolbook_ocr.schemas import (
    CanonicalDocument,
    CloudConsent,
    LayoutResult,
    PageContext,
)
from arabic_schoolbook_ocr.visualization import draw_layout_overlay, draw_reading_order_overlay

DEFAULT_PAGES = [4, 36, 53, 184, 209]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run the private five-page OCR smoke workflow")
    result.add_argument("pdf", type=Path)
    result.add_argument(
        "--mode", choices=["windows", "local", "azure", "hybrid", "mock"], default="windows"
    )
    result.add_argument("--pages", nargs="+", type=int, default=DEFAULT_PAGES)
    result.add_argument("--job-root", type=Path, default=ROOT / "jobs")
    result.add_argument("--job-id")
    result.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    result.add_argument("--cloud-opt-in", action="store_true")
    result.add_argument("--verifier", choices=["paddle", "windows"], default="paddle")
    return result


def providers(arguments: argparse.Namespace, settings: Settings):
    def windows() -> WindowsOcrProvider:
        return WindowsOcrProvider(ROOT / "scripts" / "run_windows_ocr.ps1")

    if arguments.mode == "windows":
        return windows(), FullPageLayoutProvider(), None, DisabledAdjudicator()
    if arguments.mode == "mock":
        return MockOcrProvider(), MockLayoutProvider(), None, DisabledAdjudicator()
    if arguments.mode == "local":
        return (
            PaddleLocalOcrProvider(device=arguments.device),
            PaddleLocalLayoutProvider(device=arguments.device),
            windows(),
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
    )
    return (
        AzureDocumentIntelligenceProvider(settings),
        FullPageLayoutProvider(),
        verifier,
        GeminiAdjudicator(settings),
    )


def main() -> None:
    arguments = parser().parse_args()
    settings = Settings()
    settings.assert_training_disabled()
    arguments.pdf = arguments.pdf.resolve()
    if not arguments.pdf.is_file():
        raise SystemExit(f"PDF not found: {arguments.pdf}")
    total_pages = pdf_page_count(arguments.pdf)
    invalid = [page for page in arguments.pages if page < 1 or page > total_pages]
    if invalid:
        raise SystemExit(f"Invalid pages for {total_pages}-page PDF: {invalid}")
    if arguments.mode in {"azure", "hybrid"} and not arguments.cloud_opt_in:
        raise SystemExit("Cloud modes require the explicit --cloud-opt-in flag")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    job_id = arguments.job_id or f"smoke-{arguments.mode}-{timestamp}"
    store = JobStore(arguments.job_root, job_id)
    store.initialize()
    rendered_source = render_pdf_pages(
        arguments.pdf, store.path / "source" / "rendered", arguments.pages, dpi=300
    )
    primary, layout, verifier, adjudicator = providers(arguments, settings)
    pipeline = PagePipeline(
        primary=primary,
        layout=layout,
        verifier=verifier,
        adjudicator=adjudicator,
        store=store,
    )
    source_sha256 = sha256_file(arguments.pdf)
    consent = CloudConsent(
        cloud_opt_in=arguments.cloud_opt_in,
        allowed_providers=(
            {"azure", "gemini"}
            if arguments.mode == "hybrid"
            else {"azure"}
            if arguments.mode == "azure"
            else set()
        ),
        allowed_pages=set(arguments.pages) if arguments.cloud_opt_in else None,
        allow_full_document_gemini=False,
        acknowledged_at=datetime.now(UTC) if arguments.cloud_opt_in else None,
    )
    document = CanonicalDocument(
        title=arguments.pdf.stem,
        source_filename=arguments.pdf.name,
        source_sha256=source_sha256,
        classification="EVALUATION_ONLY",
        run_configuration={
            "mode": arguments.mode,
            "pages": arguments.pages,
            "dpi": 300,
            "training_approved": False,
            "cloud_opt_in": arguments.cloud_opt_in,
            "full_document_gemini": False,
        },
    )
    store.save_json(
        "run_manifest.json",
        {
            "job_id": job_id,
            "source_filename": arguments.pdf.name,
            "source_sha256": source_sha256,
            "classification": "EVALUATION_ONLY",
            "pages": arguments.pages,
            "total_source_pages": total_pages,
            "providers": {
                "primary": primary.name,
                "layout": layout.name,
                "verifier": verifier.name if verifier else None,
                "adjudicator": adjudicator.name,
            },
            "cloud_consent": consent.model_dump(mode="json"),
            "training_approved": False,
        },
    )

    for page_number, image_path in zip(arguments.pages, rendered_source, strict=True):
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
        document.pages.append(page)
        document.pages.sort(key=lambda item: item.page_number)
        store.save_json("document/canonical_document.json", document)
        page_dir = store.page_dir(page_number)
        layout_result = (
            LayoutResult.model_validate_json((page_dir / "layout.json").read_text(encoding="utf-8"))
            if (page_dir / "layout.json").is_file()
            else None
        )
        with Image.open(page_dir / "source.png") as source:
            if layout_result is not None:
                draw_layout_overlay(source, layout_result.regions).save(
                    page_dir / "layout_overlay.png"
                )
            draw_reading_order_overlay(source, page.blocks).save(
                page_dir / "reading_order_overlay.png"
            )
        verifier_path = page_dir / "verifier.json"
        if not verifier_path.exists():
            verifier_path.write_text(
                json.dumps({"status": "not_configured"}, indent=2), encoding="utf-8"
            )

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
    store.save_json(
        "output/issue_report.json",
        {
            "accuracy_status": "UNMEASURED_PENDING_HUMAN_GROUND_TRUTH",
            "failed_pages": [page.page_number for page in document.pages if page.error],
            "unresolved": unresolved,
        },
    )
    renderer = DocxDocumentRenderer()
    literal = renderer.render_docx(document, store.path / "output" / "smoke_literal.docx")
    polished = renderer.render_docx(
        document, store.path / "output" / "smoke_polished.docx", polished=True
    )
    write_correction_reports(document, store.path / "output")
    report = write_smoke_report(document, store.path, store.path / "output" / "smoke_report.html")
    summary = {
        "job": str(store.path),
        "pages": arguments.pages,
        "completed": document.completed_pages,
        "failed": [page.page_number for page in document.pages if page.error],
        "unresolved_blocks": len(unresolved),
        "literal_docx": str(literal.output_path),
        "polished_docx": str(polished.output_path),
        "report": str(report),
        "accuracy": "UNMEASURED_PENDING_HUMAN_GROUND_TRUTH",
    }
    (store.path / "output" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
