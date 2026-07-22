from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .config import Settings
from .pdf_render import pdf_page_count, render_pdf_pages
from .persistence import JobStore
from .pipeline import PagePipeline, sha256_file
from .rendering import DocxDocumentRenderer, export_docx_to_pdf
from .reporting import write_correction_reports, write_review_report
from .runtime import build_provider_bundle
from .schemas import CanonicalDocument, CloudConsent, PageContext

MODE_ALIASES = {
    "local": "local",
    "cloud": "azure",
    "hybrid": "hybrid",
    "ai-verified": "ai_verified",
    "maximum-accuracy": "maximum_accuracy",
    "windows": "windows",
    "mock": "mock",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arabic-schoolbook-ocr")
    subcommands = parser.add_subparsers(dest="command", required=True)

    process = subcommands.add_parser("process", help="Process a PDF into semantic DOCX files")
    process.add_argument("pdf", type=Path)
    process.add_argument("--mode", choices=sorted(MODE_ALIASES), default="local")
    process.add_argument("--output-dir", type=Path)
    process.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    process.add_argument("--cloud-opt-in", action="store_true")
    process.add_argument("--full-book-confirmed", action="store_true")
    process.add_argument(
        "--ai-verification",
        choices=["off", "uncertain", "important", "every"],
        default=None,
    )
    process.add_argument(
        "--ai-formatting",
        choices=["off", "structural"],
        default=None,
    )
    process.add_argument("--ai-visual-qa", action="store_true")
    process.add_argument("--allow-full-page-gemini", action="store_true")
    process.add_argument("--literal-docx", action="store_true")
    process.add_argument("--polished-docx", action="store_true")

    render = subcommands.add_parser("render-pages", help="Render selected PDF pages locally")
    render.add_argument("pdf", type=Path)
    render.add_argument("output", type=Path)
    render.add_argument("--pages", nargs="+", type=int, required=True)
    render.add_argument("--dpi", type=int, default=300)
    return parser


def _process(arguments: argparse.Namespace) -> int:
    source = arguments.pdf.resolve()
    if not source.is_file():
        raise SystemExit(f"PDF not found: {source}")
    mode = MODE_ALIASES[arguments.mode]
    requested_ai = (
        arguments.ai_verification not in {None, "off"}
        or arguments.ai_formatting == "structural"
        or arguments.ai_visual_qa
    )
    cloud_mode = mode in {"azure", "hybrid", "ai_verified", "maximum_accuracy"} or requested_ai
    if cloud_mode and not arguments.cloud_opt_in:
        raise SystemExit("Cloud modes require --cloud-opt-in")
    total_pages = pdf_page_count(source)
    if cloud_mode and total_pages > 5 and not arguments.full_book_confirmed:
        raise SystemExit("Cloud runs over five pages require --full-book-confirmed")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (
        arguments.output_dir.resolve()
        if arguments.output_dir
        else (Path.cwd() / "output" / f"{source.stem}-{timestamp}").resolve()
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    store = JobStore(output_dir.parent, output_dir.name)
    store.initialize()
    settings = Settings(job_root=output_dir.parent)
    settings.assert_training_disabled()
    verification_scope = arguments.ai_verification
    if verification_scope is None:
        verification_scope = (
            "important" if mode in {"hybrid", "ai_verified", "maximum_accuracy"} else "off"
        )
    if verification_scope != "off" and not settings.enable_gemini_verification:
        raise SystemExit(
            "Gemini verification was requested but ENABLE_GEMINI_VERIFICATION is false"
        )
    formatting_enabled = (
        arguments.ai_formatting == "structural"
        if arguments.ai_formatting is not None
        else mode == "maximum_accuracy"
    )
    visual_qa_enabled = arguments.ai_visual_qa or mode == "maximum_accuracy"
    if formatting_enabled and not settings.enable_gemini_formatting:
        raise SystemExit("Gemini formatting was requested but ENABLE_GEMINI_FORMATTING is false")
    if visual_qa_enabled and not settings.enable_gemini_visual_qa:
        raise SystemExit("Gemini visual QA was requested but ENABLE_GEMINI_VISUAL_QA is false")
    if (formatting_enabled or visual_qa_enabled) and not arguments.allow_full_page_gemini:
        raise SystemExit(
            "Formatting and visual QA require the separate --allow-full-page-gemini consent"
        )
    bundle = build_provider_bundle(
        mode,
        settings,
        project_root=Path(__file__).resolve().parents[2],
        device=arguments.device,
        verification_scope=verification_scope,
        formatting_enabled=formatting_enabled,
        visual_qa_enabled=visual_qa_enabled,
    )
    providers: set[str] = set()
    if mode in {"azure", "hybrid", "maximum_accuracy"}:
        providers.add("azure")
    if verification_scope != "off":
        providers.add("gemini")
    consent = CloudConsent(
        cloud_opt_in=arguments.cloud_opt_in,
        allowed_providers=providers,
        allowed_pages=set(range(1, total_pages + 1)) if arguments.cloud_opt_in else None,
        allow_full_document_gemini=arguments.allow_full_page_gemini,
        acknowledged_at=datetime.now(timezone.utc) if arguments.cloud_opt_in else None,
    )
    source_hash = sha256_file(source)
    document = CanonicalDocument(
        title=source.stem,
        source_filename=source.name,
        source_sha256=source_hash,
        classification="EVALUATION_ONLY",
        run_configuration={
            "mode": mode,
            "device": arguments.device,
            "cloud_opt_in": arguments.cloud_opt_in,
            "verification_scope": verification_scope,
            "formatting_enabled": formatting_enabled,
            "visual_qa_enabled": visual_qa_enabled,
            "allow_full_page_gemini": arguments.allow_full_page_gemini,
            "training_approved": False,
        },
    )
    pipeline = PagePipeline(
        primary=bundle.primary,
        layout=bundle.layout,
        verifier=bundle.verifier,
        adjudicator=bundle.adjudicator,
        verification_policy=bundle.verification_policy,
        formatting_analyst=bundle.formatting_analyst,
        automatic_correction_confidence_threshold=(
            settings.gemini_correction_confidence_threshold
        ),
        store=store,
    )
    rendered = render_pdf_pages(
        source,
        store.path / "source" / "rendered",
        list(range(1, total_pages + 1)),
        dpi=300,
    )
    for page_number, image_path in enumerate(rendered, start=1):
        with Image.open(image_path) as page_image:
            page = pipeline.process_page(
                page_image.copy(),
                PageContext(
                    job_id=store.job_id,
                    page_number=page_number,
                    total_pages=total_pages,
                    source_sha256=source_hash,
                    consent=consent,
                ),
            )
        document.pages.append(page)
        store.save_json("document/canonical_document.json", document)

    renderer = DocxDocumentRenderer()
    render_literal = arguments.literal_docx or not arguments.polished_docx
    render_polished = arguments.polished_docx or not arguments.literal_docx
    outputs: dict[str, str] = {}
    qa_docx: Path | None = None
    if render_literal:
        literal = renderer.render_docx(
            document, store.path / "output" / f"{source.stem}_literal.docx"
        )
        outputs["literal_docx"] = str(literal.output_path)
        qa_docx = literal.output_path
    if render_polished:
        polished = renderer.render_docx(
            document,
            store.path / "output" / f"{source.stem}_polished.docx",
            polished=True,
        )
        outputs["polished_docx"] = str(polished.output_path)
        qa_docx = polished.output_path
    correction_json, correction_html = write_correction_reports(
        document, store.path / "output"
    )
    review = write_review_report(
        document, store.path, store.path / "output" / "review_report.html"
    )
    outputs.update(
        {
            "correction_json": str(correction_json),
            "correction_html": str(correction_html),
            "review_report": str(review),
        }
    )
    visual_qa_status = "NOT_REQUESTED"
    if bundle.visual_qa is not None and qa_docx is not None:
        visual_qa_results: list[dict[str, object]] = []
        try:
            rendered_docx_pdf = export_docx_to_pdf(
                qa_docx, store.path / "output" / "visual_qa_rendered.pdf"
            )
            rendered_docx_pages = render_pdf_pages(
                rendered_docx_pdf,
                store.path / "output" / "visual_qa_rendered_pages",
                list(range(1, total_pages + 1)),
                dpi=150,
            )
            for page, source_path, rendered_path in zip(
                document.pages, rendered, rendered_docx_pages, strict=True
            ):
                try:
                    with Image.open(source_path) as source_image, Image.open(
                        rendered_path
                    ) as rendered_image:
                        response = bundle.visual_qa.evaluate(
                            source_image.copy(),
                            rendered_image.copy(),
                            page,
                            PageContext(
                                job_id=store.job_id,
                                page_number=page.page_number,
                                total_pages=total_pages,
                                source_sha256=source_hash,
                                consent=consent,
                            ),
                        )
                    page.usage.append(response.usage)
                    visual_qa_results.append(
                        {
                            "page_number": page.page_number,
                            "state": "COMPLETED",
                            "result": response.result.model_dump(mode="json"),
                        }
                    )
                except Exception as exc:
                    visual_qa_results.append(
                        {
                            "page_number": page.page_number,
                            "state": "FAILED_AI",
                            "error_type": type(exc).__name__,
                        }
                    )
            visual_qa_status = (
                "COMPLETED_WITH_AI_ERRORS"
                if any(item["state"] == "FAILED_AI" for item in visual_qa_results)
                else "COMPLETED"
            )
        except Exception as exc:
            visual_qa_status = "FAILED_AI"
            visual_qa_results = [{"state": "FAILED_AI", "error_type": type(exc).__name__}]
        store.save_json(
            "output/visual_qa_report.json",
            {"status": visual_qa_status, "pages": visual_qa_results},
        )
        store.save_json("document/canonical_document.json", document)
    manifest = {
        "status": (
            "COMPLETED"
            if document.completed_pages == total_pages
            else "COMPLETED_WITH_ERRORS"
        ),
        "source_sha256": source_hash,
        "classification": "EVALUATION_ONLY",
        "total_pages": total_pages,
        "completed_pages": document.completed_pages,
        "mode": mode,
        "cloud_consent": consent.model_dump(mode="json"),
        "providers": {
            "primary": bundle.primary.name,
            "layout": bundle.layout.name,
            "verifier": bundle.verifier.name if bundle.verifier else None,
            "adjudicator": bundle.adjudicator.name,
        },
        "api_calls": sum(usage.api_calls for page in document.pages for usage in page.usage),
        "estimated_cost": sum(
            usage.estimated_cost or 0 for page in document.pages for usage in page.usage
        ),
        "unresolved_blocks": sum(
            block.unresolved for page in document.pages for block in page.blocks
        ),
        "accuracy": "UNMEASURED_PENDING_HUMAN_GROUND_TRUTH",
        "visual_qa_status": visual_qa_status,
        "outputs": outputs,
    }
    store.save_json("run_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    arguments = _parser().parse_args()
    if arguments.command == "render-pages":
        for path in render_pdf_pages(
            arguments.pdf, arguments.output, arguments.pages, dpi=arguments.dpi
        ):
            print(path)
        return
    raise SystemExit(_process(arguments))
