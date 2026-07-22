from __future__ import annotations

import json
import platform
import re
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field, SecretStr

from .config import Settings
from .pdf_render import pdf_page_count, render_pdf_pages
from .persistence import JobStore, atomic_write_json
from .pipeline import PagePipeline, sha256_file
from .providers import UnlimitedOcrProvider
from .rendering import DocxDocumentRenderer, DocxPdfExportError, export_docx_to_pdf
from .reporting import write_correction_reports, write_review_report
from .runtime import build_provider_bundle
from .schemas import (
    BlockType,
    BoundaryDecision,
    BoundingBox,
    CanonicalBlock,
    CanonicalDocument,
    CanonicalPage,
    CloudConsent,
    Direction,
    LayoutResult,
    PageContext,
    PageStatus,
    TableData,
    TextRun,
)
from .visualization import draw_layout_overlay, draw_reading_order_overlay

PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_MODES = {
    "local",
    "windows",
    "azure",
    "hybrid",
    "ai_verified",
    "maximum_accuracy",
    "unlimited",
    "mock",
}


class BlockPatch(BaseModel):
    approved_corrected_text: str | None = None
    block_type: BlockType | None = None
    reading_order: int | None = Field(default=None, ge=0)
    bbox: BoundingBox | None = None
    paragraph_direction: Direction | None = None
    paragraph_group_id: str | None = None
    boundaries: list[BoundaryDecision] | None = None
    runs: list[TextRun] | None = None
    table: TableData | None = None
    reason: str = "Human review"
    human_approved: bool = False


class NewBlock(BaseModel):
    block_type: BlockType = BlockType.UNKNOWN
    bbox: BoundingBox
    text: str
    reading_order: int = Field(ge=0)
    reason: str = "Human-added missing block"
    human_approved: bool = False


class RetryRequest(BaseModel):
    cloud_opt_in: bool = False


class SettingsPatch(BaseModel):
    azure_document_intelligence_endpoint: str | None = None
    azure_document_intelligence_key: SecretStr | None = Field(default=None, repr=False)
    gemini_api_key: SecretStr | None = Field(default=None, repr=False)
    gemini_model: str | None = None
    enable_gemini_verification: bool | None = None
    enable_gemini_formatting: bool | None = None
    enable_gemini_visual_qa: bool | None = None
    clear_azure_key: bool = False
    clear_gemini_key: bool = False


def _public_settings(settings: Settings) -> dict[str, Any]:
    return {
        "azure_endpoint_configured": bool(settings.azure_document_intelligence_endpoint),
        "azure_key_configured": settings.azure_document_intelligence_key is not None,
        "gemini_key_configured": settings.gemini_api_key is not None,
        "gemini_model": settings.gemini_model,
        "enable_gemini_verification": settings.enable_gemini_verification,
        "enable_gemini_formatting": settings.enable_gemini_formatting,
        "enable_gemini_visual_qa": settings.enable_gemini_visual_qa,
        "gemini_verify_confidence_threshold": settings.gemini_verify_confidence_threshold,
        "gemini_max_retries": settings.gemini_max_retries,
        "gemini_max_parallel_requests": settings.gemini_max_parallel_requests,
        "secrets_persisted": False,
        "note": "Keys entered in Settings are held only for this server process.",
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _job_root(settings: Settings) -> Path:
    configured = settings.job_root
    return (configured if configured.is_absolute() else PROJECT_ROOT / configured).resolve()


def _job_path(settings: Settings, job_id: str) -> Path:
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Unsafe job identifier")
    root = _job_root(settings)
    path = (root / job_id).resolve()
    if root not in path.parents:
        raise HTTPException(status_code=400, detail="Job path escapes configured storage")
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="Job not found")
    return path


def _parse_pages(selection: str, total_pages: int) -> list[int]:
    normalized = selection.strip().lower()
    if normalized in {"first5", "smoke"}:
        return list(range(1, min(total_pages, 5) + 1))
    if normalized == "all":
        return list(range(1, total_pages + 1))
    try:
        pages = sorted({int(value.strip()) for value in selection.split(",") if value.strip()})
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Pages must be all, first5, or comma-separated"
        ) from exc
    if not pages or any(page < 1 or page > total_pages for page in pages):
        raise HTTPException(status_code=422, detail=f"Pages must be within 1..{total_pages}")
    return pages


def _save_status(store: JobStore, **updates: Any) -> dict[str, Any]:
    loaded = _read_json(store.path / "status.json", {})
    current: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
    current.update(updates)
    current["updated_at"] = _now()
    store.save_json("status.json", current)
    return current


def _export_document(document: CanonicalDocument, store: JobStore) -> dict[str, str]:
    renderer = DocxDocumentRenderer()
    literal = renderer.render_docx(document, store.path / "output" / "literal.docx")
    polished = renderer.render_docx(
        document, store.path / "output" / "polished.docx", polished=True
    )
    correction_json, correction_html = write_correction_reports(document, store.path / "output")
    report = write_review_report(document, store.path, store.path / "output" / "review_report.html")
    outputs = {
        "literal_docx": str(literal.output_path.relative_to(store.path)).replace("\\", "/"),
        "polished_docx": str(polished.output_path.relative_to(store.path)).replace("\\", "/"),
        "correction_json": str(correction_json.relative_to(store.path)).replace("\\", "/"),
        "correction_html": str(correction_html.relative_to(store.path)).replace("\\", "/"),
        "review_report": str(report.relative_to(store.path)).replace("\\", "/"),
    }
    try:
        rendered_pdf = export_docx_to_pdf(
            polished.output_path, store.path / "output" / "rendered.pdf"
        )
        outputs["rendered_pdf"] = str(rendered_pdf.relative_to(store.path)).replace("\\", "/")
        store.save_json("output/render_status.json", {"available": True, "error": None})
    except DocxPdfExportError as exc:
        store.save_json("output/render_status.json", {"available": False, "error": str(exc)})
    return outputs


def _execute_job(
    *,
    settings: Settings,
    job_id: str,
    pdf_path: Path,
    original_filename: str,
    mode: str,
    pages: list[int],
    total_pages: int,
    device: str,
    cloud_opt_in: bool,
    verification_scope: str = "off",
    formatting_mode: str = "off",
    visual_qa_enabled: bool = False,
    allow_full_page_gemini: bool = False,
    resume_existing: bool = False,
) -> None:
    store = JobStore(_job_root(settings), job_id)
    try:
        settings.assert_training_disabled()
        bundle = build_provider_bundle(
            mode,
            settings,
            project_root=PROJECT_ROOT,
            device=device,
            verification_scope=verification_scope,
            formatting_enabled=formatting_mode != "off",
            visual_qa_enabled=visual_qa_enabled,
        )
        source_sha256 = sha256_file(pdf_path)
        allowed_providers: set[str] = set()
        if mode in {"azure", "hybrid", "maximum_accuracy"}:
            allowed_providers.add("azure")
        if verification_scope != "off" or formatting_mode != "off" or visual_qa_enabled:
            allowed_providers.add("gemini")
        consent = CloudConsent(
            cloud_opt_in=cloud_opt_in,
            allowed_providers=allowed_providers,
            allowed_pages=set(pages) if cloud_opt_in else None,
            allow_full_document_gemini=allow_full_page_gemini,
            acknowledged_at=datetime.now(timezone.utc) if cloud_opt_in else None,
        )
        canonical_path = store.path / "document" / "canonical_document.json"
        document = (
            CanonicalDocument.model_validate_json(canonical_path.read_text(encoding="utf-8"))
            if resume_existing and canonical_path.is_file()
            else CanonicalDocument(
                title=Path(original_filename).stem,
                source_filename=original_filename,
                source_sha256=source_sha256,
                classification="EVALUATION_ONLY",
                run_configuration={
                    "mode": mode,
                    "pages": pages,
                    "device": device,
                    "dpi": 300,
                    "training_approved": False,
                    "cloud_opt_in": cloud_opt_in,
                    "gemini_verification_scope": verification_scope,
                    "gemini_formatting_mode": formatting_mode,
                    "gemini_visual_qa": visual_qa_enabled,
                    "full_document_gemini": allow_full_page_gemini,
                },
            )
        )
        if document.source_sha256 != source_sha256:
            raise ValueError("Resume refused because the source PDF hash changed")
        store.save_json(
            "run_manifest.json",
            {
                "job_id": job_id,
                "source_filename": original_filename,
                "source_sha256": source_sha256,
                "classification": "EVALUATION_ONLY",
                "pages": pages,
                "total_source_pages": total_pages,
                "mode": mode,
                "device": device,
                "ai_configuration": {
                    "verification_scope": verification_scope,
                    "formatting_mode": formatting_mode,
                    "visual_qa": visual_qa_enabled,
                    "allow_full_page_gemini": allow_full_page_gemini,
                    "model": settings.gemini_model,
                },
                "providers": {
                    "primary": bundle.primary.name,
                    "layout": bundle.layout.name,
                    "verifier": bundle.verifier.name if bundle.verifier else None,
                    "adjudicator": bundle.adjudicator.name,
                    "formatting": (
                        bundle.formatting_analyst.name if bundle.formatting_analyst else None
                    ),
                    "visual_qa": bundle.visual_qa.name if bundle.visual_qa else None,
                },
                "runtime_versions": {
                    "paddlepaddle": _package_version("paddlepaddle"),
                    "paddleocr": _package_version("paddleocr"),
                    "paddlex": _package_version("paddlex"),
                },
                "cloud_consent": consent.model_dump(mode="json"),
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
        job_started = datetime.now(timezone.utc)
        _save_status(
            store,
            state="RUNNING",
            started_at=job_started.isoformat(),
            processed_pages=0,
            current_stage="render-page",
        )
        for index, page_number in enumerate(pages, start=1):
            status = _read_json(store.path / "status.json", {})
            if status.get("cancel_requested"):
                _save_status(store, state="CANCELLED", completed_at=_now())
                return
            _save_status(store, current_page=page_number, current_stage="render-page")
            try:
                rendered = render_pdf_pages(
                    pdf_path,
                    store.path / "source" / "rendered",
                    [page_number],
                    dpi=300,
                )[0]
                _save_status(store, current_stage="layout-and-ocr")
                with Image.open(rendered) as source:
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
            document.pages = [item for item in document.pages if item.page_number != page_number]
            document.pages.append(page)
            document.pages.sort(key=lambda item: item.page_number)
            store.save_json("document/canonical_document.json", document)
            page_dir = store.page_dir(page_number)
            layout_path = page_dir / "layout.json"
            layout_result = (
                LayoutResult.model_validate_json(layout_path.read_text(encoding="utf-8"))
                if layout_path.is_file()
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
            _save_status(
                store,
                processed_pages=index,
                failed_pages=[item.page_number for item in document.pages if item.error],
                warnings=sum(len(item.warnings) for item in document.pages),
                api_calls=sum(usage.api_calls for item in document.pages for usage in item.usage),
                estimated_cloud_cost=sum(
                    usage.estimated_cost or 0 for item in document.pages for usage in item.usage
                ),
                elapsed_seconds=round(
                    (datetime.now(timezone.utc) - job_started).total_seconds(), 1
                ),
            )
        _save_status(store, current_stage="export")
        outputs = _export_document(document, store)
        visual_qa_summary: dict[str, Any] | None = None
        if bundle.visual_qa is not None and "rendered_pdf" in outputs:
            _save_status(store, current_stage="gemini-rendered-word-qa")
            qa_results: list[dict[str, Any]] = []
            rendered_pdf_path = store.path / outputs["rendered_pdf"]
            rendered_pages = render_pdf_pages(
                rendered_pdf_path,
                store.path / "output" / "visual_qa_rendered",
                list(range(1, len(document.pages) + 1)),
                dpi=150,
            )
            for page, rendered_page_path in zip(
                sorted(document.pages, key=lambda item: item.page_number),
                rendered_pages,
                strict=True,
            ):
                try:
                    with (
                        Image.open(store.path / page.source_image) as source_image,
                        Image.open(rendered_page_path) as rendered_image,
                    ):
                        qa_response = bundle.visual_qa.evaluate(
                            source_image.copy(),
                            rendered_image.copy(),
                            page,
                            PageContext(
                                job_id=job_id,
                                page_number=page.page_number,
                                total_pages=total_pages,
                                source_sha256=source_sha256,
                                consent=consent,
                            ),
                        )
                    page.usage.append(qa_response.usage)
                    qa_results.append(
                        {
                            "page_number": page.page_number,
                            "status": "COMPLETED",
                            "result": qa_response.result.model_dump(mode="json"),
                            "usage": qa_response.usage.model_dump(mode="json"),
                        }
                    )
                except Exception as exc:
                    qa_results.append(
                        {
                            "page_number": page.page_number,
                            "status": "FAILED",
                            "error_type": type(exc).__name__,
                        }
                    )
            visual_qa_summary = {
                "agent": bundle.visual_qa.name,
                "pages_requested": len(document.pages),
                "pages_completed": sum(item["status"] == "COMPLETED" for item in qa_results),
                "failed_requests": sum(item["status"] == "FAILED" for item in qa_results),
                "pages_passed": sum(
                    bool(item.get("result", {}).get("page_passed")) for item in qa_results
                ),
                "results": qa_results,
                "note": "QA reports issues only; it never modifies DOCX content directly.",
            }
            store.save_json("output/visual_qa_report.json", visual_qa_summary)
            store.save_json("document/canonical_document.json", document)
            outputs["visual_qa_report"] = "output/visual_qa_report.json"
        failed = [page.page_number for page in document.pages if page.error]
        summary = {
            "job_id": job_id,
            "pages": pages,
            "completed": document.completed_pages,
            "failed": failed,
            "unresolved_blocks": sum(
                block.unresolved for page in document.pages for block in page.blocks
            ),
            "outputs": outputs,
            "visual_qa": visual_qa_summary,
            "accuracy": "UNMEASURED_PENDING_HUMAN_GROUND_TRUTH",
        }
        store.save_json("output/summary.json", summary)
        _save_status(
            store,
            state="COMPLETED_WITH_ERRORS" if failed else "COMPLETED",
            current_page=None,
            completed_at=_now(),
            outputs=outputs,
            accuracy_status="UNMEASURED_PENDING_HUMAN_GROUND_TRUTH",
            unresolved_blocks=summary["unresolved_blocks"],
            api_calls=sum(usage.api_calls for item in document.pages for usage in item.usage),
            estimated_cloud_cost=sum(
                usage.estimated_cost or 0 for item in document.pages for usage in item.usage
            ),
            failed_ai_requests=(
                visual_qa_summary.get("failed_requests", 0) if visual_qa_summary else 0
            ),
        )
    except Exception as exc:
        _save_status(
            store,
            state="FAILED",
            completed_at=_now(),
            error=f"{type(exc).__name__}: {exc}",
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings()
    runtime_settings.assert_training_disabled()
    jobs_root = _job_root(runtime_settings)
    jobs_root.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Arabic Schoolbook OCR", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "privacy": "local-private-by-default",
            "training": "disabled",
        }

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return _public_settings(runtime_settings)

    @app.post("/api/settings")
    def update_settings(patch: SettingsPatch) -> dict[str, Any]:
        """Update process-local provider settings without ever returning secrets."""

        if patch.clear_azure_key:
            runtime_settings.azure_document_intelligence_key = None
        elif patch.azure_document_intelligence_key is not None:
            runtime_settings.azure_document_intelligence_key = SecretStr(
                patch.azure_document_intelligence_key.get_secret_value()
            )
        if patch.clear_gemini_key:
            runtime_settings.gemini_api_key = None
        elif patch.gemini_api_key is not None:
            runtime_settings.gemini_api_key = SecretStr(patch.gemini_api_key.get_secret_value())
        if patch.azure_document_intelligence_endpoint is not None:
            runtime_settings.azure_document_intelligence_endpoint = (
                patch.azure_document_intelligence_endpoint.strip() or None
            )
        if patch.gemini_model is not None:
            runtime_settings.gemini_model = patch.gemini_model.strip() or "gemini-3.6-flash"
        for field_name in (
            "enable_gemini_verification",
            "enable_gemini_formatting",
            "enable_gemini_visual_qa",
        ):
            value = getattr(patch, field_name)
            if value is not None:
                setattr(runtime_settings, field_name, value)
        return _public_settings(runtime_settings)

    @app.get("/api/providers")
    def providers() -> dict[str, Any]:
        unlimited = UnlimitedOcrProvider(runtime_settings).preflight()
        azure_ready = bool(
            runtime_settings.azure_document_intelligence_endpoint
            and runtime_settings.azure_document_intelligence_key
        )
        gemini_ready = runtime_settings.gemini_api_key is not None
        return {
            "local": {
                "available": all(
                    _package_version(name) is not None
                    for name in ("paddlepaddle", "paddleocr", "paddlex")
                ),
                "private": True,
                "versions": {
                    name: _package_version(name)
                    for name in ("paddlepaddle", "paddleocr", "paddlex")
                },
            },
            "windows": {
                "available": platform.system() == "Windows"
                and (PROJECT_ROOT / "scripts/run_windows_ocr.ps1").is_file()
            },
            "azure": {"available": azure_ready, "requires_cloud_opt_in": True},
            "gemini": {
                "available": gemini_ready,
                "requires_cloud_opt_in": True,
                "model": runtime_settings.gemini_model,
                "verification_enabled": runtime_settings.enable_gemini_verification,
                "formatting_enabled": runtime_settings.enable_gemini_formatting,
                "visual_qa_enabled": runtime_settings.enable_gemini_visual_qa,
            },
            "ai_verified": {
                "available": gemini_ready and runtime_settings.enable_gemini_verification,
                "requires_cloud_opt_in": True,
                "gemini_scope": "consented triggered crops",
            },
            "hybrid": {
                "available": azure_ready and gemini_ready,
                "requires_cloud_opt_in": True,
                "gemini_scope": "disputed crops only",
            },
            "maximum_accuracy": {
                "available": azure_ready
                and gemini_ready
                and runtime_settings.enable_gemini_verification,
                "requires_cloud_opt_in": True,
                "gemini_scope": "consented crops and optional selected full pages",
            },
            "unlimited": {
                "available": unlimited.available,
                "mode": unlimited.mode,
                "gpu_memory_mb": unlimited.gpu_memory_mb,
                "reason": unlimited.reason,
            },
        }

    @app.get("/api/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for path in sorted(
            jobs_root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True
        ):
            if not path.is_dir() or not JOB_ID_PATTERN.fullmatch(path.name):
                continue
            status = _read_json(path / "status.json", {})
            summary = _read_json(path / "output" / "summary.json", {})
            manifest = _read_json(path / "run_manifest.json", {})
            if not status and summary:
                status = {
                    "state": "COMPLETED",
                    "processed_pages": summary.get("completed", 0),
                    "accuracy_status": summary.get("accuracy"),
                }
            results.append(
                {
                    "job_id": path.name,
                    "status": status,
                    "summary": summary,
                    "manifest": manifest,
                }
            )
        return results

    @app.post("/api/jobs", status_code=202)
    async def create_job(
        background_tasks: BackgroundTasks,
        file: Annotated[UploadFile, File()],
        mode: Annotated[str, Form()] = "local",
        pages: Annotated[str, Form()] = "first5",
        device: Annotated[str, Form()] = "cpu",
        cloud_opt_in: Annotated[bool, Form()] = False,
        full_book_confirmed: Annotated[bool, Form()] = False,
        ai_verification: Annotated[
            Literal["off", "uncertain", "important", "every"], Form()
        ] = "off",
        ai_formatting: Annotated[
            Literal["off", "structural", "structural_suggestions"], Form()
        ] = "off",
        ai_visual_qa: Annotated[bool, Form()] = False,
        allow_full_page_gemini: Annotated[bool, Form()] = False,
    ) -> dict[str, Any]:
        if mode not in ALLOWED_MODES:
            raise HTTPException(status_code=422, detail="Unknown provider mode")
        if device not in {"cpu", "gpu"}:
            raise HTTPException(status_code=422, detail="Device must be cpu or gpu")
        uses_azure = mode in {"azure", "hybrid", "maximum_accuracy"}
        uses_gemini = (
            mode in {"ai_verified", "maximum_accuracy"}
            or ai_verification != "off"
            or ai_formatting != "off"
            or ai_visual_qa
        )
        if (uses_azure or uses_gemini) and not cloud_opt_in:
            raise HTTPException(status_code=403, detail="Cloud mode requires explicit opt-in")
        if uses_azure and not (
            runtime_settings.azure_document_intelligence_endpoint
            and runtime_settings.azure_document_intelligence_key
        ):
            raise HTTPException(status_code=503, detail="Azure credentials are not configured")
        if uses_gemini and runtime_settings.gemini_api_key is None:
            raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured")
        if ai_verification != "off" and not runtime_settings.enable_gemini_verification:
            raise HTTPException(status_code=403, detail="Gemini verification is disabled")
        if ai_formatting != "off" and not runtime_settings.enable_gemini_formatting:
            raise HTTPException(status_code=403, detail="Gemini formatting is disabled")
        if ai_visual_qa and not runtime_settings.enable_gemini_visual_qa:
            raise HTTPException(status_code=403, detail="Gemini visual QA is disabled")
        if (ai_formatting != "off" or ai_visual_qa) and not allow_full_page_gemini:
            raise HTTPException(
                status_code=403,
                detail="Formatting or visual QA requires separate selected-full-page consent",
            )
        if mode == "unlimited":
            preflight = UnlimitedOcrProvider(runtime_settings).preflight()
            if not preflight.available:
                raise HTTPException(status_code=503, detail=preflight.reason)
        job_id = f"job-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        store = JobStore(jobs_root, job_id)
        store.initialize()
        destination = store.path / "source" / "input.pdf"
        maximum = runtime_settings.max_upload_mb * 1024 * 1024
        size = 0
        with destination.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > maximum:
                    target.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="PDF exceeds configured size limit")
                target.write(chunk)
        await file.close()
        with destination.open("rb") as source:
            signature = source.read(5)
        if size < 5 or signature != b"%PDF-":
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail="Uploaded file is not a PDF")
        try:
            total_pages = pdf_page_count(destination)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail="PDF could not be parsed") from exc
        selected_pages = _parse_pages(pages, total_pages)
        if len(selected_pages) > 5 and not full_book_confirmed:
            raise HTTPException(
                status_code=409,
                detail="Runs over five pages require explicit full_book_confirmed=true",
            )
        original_filename = Path(file.filename or "uploaded.pdf").name
        _save_status(
            store,
            job_id=job_id,
            state="QUEUED",
            mode=mode,
            total_pages=total_pages,
            selected_pages=selected_pages,
            processed_pages=0,
            cancel_requested=False,
            cloud_opt_in=cloud_opt_in,
            ai_verification=ai_verification,
            ai_formatting=ai_formatting,
            ai_visual_qa=ai_visual_qa,
            allow_full_page_gemini=allow_full_page_gemini,
            training_approved=False,
            accuracy_status="UNMEASURED_PENDING_HUMAN_GROUND_TRUTH",
        )
        background_tasks.add_task(
            _execute_job,
            settings=runtime_settings,
            job_id=job_id,
            pdf_path=destination,
            original_filename=original_filename,
            mode=mode,
            pages=selected_pages,
            total_pages=total_pages,
            device=device,
            cloud_opt_in=cloud_opt_in,
            verification_scope=ai_verification,
            formatting_mode=ai_formatting,
            visual_qa_enabled=ai_visual_qa,
            allow_full_page_gemini=allow_full_page_gemini,
        )
        return {"job_id": job_id, "state": "QUEUED", "selected_pages": selected_pages}

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry_job(
        job_id: str,
        background_tasks: BackgroundTasks,
        retry: RetryRequest,
    ) -> dict[str, Any]:
        path = _job_path(runtime_settings, job_id)
        status = _read_json(path / "status.json", {})
        if status.get("state") not in {
            "COMPLETED_WITH_ERRORS",
            "FAILED",
            "CANCELLED",
        }:
            raise HTTPException(status_code=409, detail="Only terminal jobs can be retried")
        document_path = path / "document" / "canonical_document.json"
        if not document_path.is_file():
            raise HTTPException(status_code=409, detail="No checkpoint is available")
        document = CanonicalDocument.model_validate_json(document_path.read_text(encoding="utf-8"))
        failed_pages = [page.page_number for page in document.pages if page.error]
        if not failed_pages:
            raise HTTPException(status_code=409, detail="The job has no failed pages")
        manifest = _read_json(path / "run_manifest.json", {})
        mode = str(manifest.get("mode") or status.get("mode") or "local")
        ai_configuration = manifest.get("ai_configuration", {})
        if mode in {"azure", "hybrid", "ai_verified", "maximum_accuracy"} and not (
            retry.cloud_opt_in
        ):
            raise HTTPException(status_code=403, detail="Cloud retry requires explicit opt-in")
        pdf_path = path / "source" / "input.pdf"
        if not pdf_path.is_file():
            raise HTTPException(status_code=409, detail="Original upload is unavailable")
        _save_status(
            JobStore(jobs_root, job_id),
            state="QUEUED",
            selected_pages=failed_pages,
            processed_pages=0,
            failed_pages=failed_pages,
            cancel_requested=False,
            cloud_opt_in=retry.cloud_opt_in,
        )
        background_tasks.add_task(
            _execute_job,
            settings=runtime_settings,
            job_id=job_id,
            pdf_path=pdf_path,
            original_filename=document.source_filename,
            mode=mode,
            pages=failed_pages,
            total_pages=int(manifest.get("total_source_pages") or len(document.pages)),
            device=str(document.run_configuration.get("device", "cpu")),
            cloud_opt_in=retry.cloud_opt_in,
            verification_scope=str(ai_configuration.get("verification_scope", "off")),
            formatting_mode=str(ai_configuration.get("formatting_mode", "off")),
            visual_qa_enabled=bool(ai_configuration.get("visual_qa", False)),
            allow_full_page_gemini=bool(ai_configuration.get("allow_full_page_gemini", False)),
            resume_existing=True,
        )
        return {"job_id": job_id, "state": "QUEUED", "retry_pages": failed_pages}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        path = _job_path(runtime_settings, job_id)
        document = _read_json(path / "document" / "canonical_document.json")
        return {
            "job_id": job_id,
            "status": _read_json(path / "status.json", {}),
            "manifest": _read_json(path / "run_manifest.json", {}),
            "summary": _read_json(path / "output" / "summary.json", {}),
            "document": document,
        }

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        path = _job_path(runtime_settings, job_id)
        store = JobStore(jobs_root, job_id)
        loaded = _read_json(path / "status.json", {})
        status: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
        if status.get("state") in {"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "CANCELLED"}:
            return status
        return _save_status(store, cancel_requested=True)

    @app.get("/api/jobs/{job_id}/pages/{page_number}")
    def get_page(job_id: str, page_number: int) -> dict[str, Any]:
        path = _job_path(runtime_settings, job_id)
        page_path = path / "pages" / f"{page_number:04d}" / "canonical.json"
        loaded = _read_json(page_path)
        if not isinstance(loaded, dict):
            raise HTTPException(status_code=404, detail="Page checkpoint not found")
        page: dict[str, Any] = loaded
        base = f"/api/jobs/{job_id}/files/pages/{page_number:04d}"
        page["assets"] = {
            "source": f"{base}/source.png",
            "preprocessed": f"{base}/preprocessed.png",
            "layout_overlay": f"{base}/layout_overlay.png",
            "reading_order_overlay": f"{base}/reading_order_overlay.png",
        }
        return page

    @app.patch("/api/jobs/{job_id}/pages/{page_number}/blocks/{block_id}")
    def patch_block(
        job_id: str, page_number: int, block_id: str, patch: BlockPatch
    ) -> dict[str, Any]:
        if not patch.human_approved:
            raise HTTPException(status_code=422, detail="Human approval is required")
        path = _job_path(runtime_settings, job_id)
        document_path = path / "document" / "canonical_document.json"
        document = CanonicalDocument.model_validate_json(document_path.read_text(encoding="utf-8"))
        page = next((item for item in document.pages if item.page_number == page_number), None)
        if page is None:
            raise HTTPException(status_code=404, detail="Page not found")
        block = next((item for item in page.blocks if item.id == block_id), None)
        if block is None:
            raise HTTPException(status_code=404, detail="Block not found")
        if patch.approved_corrected_text is not None:
            block.approved_corrected_text = patch.approved_corrected_text
        if patch.block_type is not None:
            block.block_type = patch.block_type
        if patch.reading_order is not None:
            block.reading_order = patch.reading_order
        if patch.bbox is not None:
            block.bbox = patch.bbox
        if patch.paragraph_direction is not None:
            block.paragraph_direction = patch.paragraph_direction
        if patch.paragraph_group_id is not None:
            block.paragraph_group_id = patch.paragraph_group_id
        if patch.boundaries is not None:
            block.boundaries = patch.boundaries
        if patch.runs is not None:
            block.runs = patch.runs
        if patch.table is not None:
            block.table = patch.table
        block.unresolved = False
        block.evidence["human_approval"] = {
            "reason": patch.reason,
            "confidence": 1.0,
            "approved_at": _now(),
            "automatic": False,
        }
        atomic_write_json(path / "pages" / f"{page_number:04d}" / "canonical.json", page)
        atomic_write_json(document_path, document)
        write_correction_reports(document, path / "output")
        return block.model_dump(mode="json")

    @app.post("/api/jobs/{job_id}/pages/{page_number}/blocks", status_code=201)
    def add_block(job_id: str, page_number: int, new_block: NewBlock) -> dict[str, Any]:
        if not new_block.human_approved:
            raise HTTPException(status_code=422, detail="Human approval is required")
        path = _job_path(runtime_settings, job_id)
        document_path = path / "document" / "canonical_document.json"
        document = CanonicalDocument.model_validate_json(document_path.read_text(encoding="utf-8"))
        page = next((item for item in document.pages if item.page_number == page_number), None)
        if page is None:
            raise HTTPException(status_code=404, detail="Page not found")
        block = CanonicalBlock(
            block_type=new_block.block_type,
            bbox=new_block.bbox,
            reading_order=new_block.reading_order,
            literal_text="",
            unicode_normalized_text="",
            approved_corrected_text=new_block.text,
            confidence=1.0,
            unresolved=False,
            evidence={
                "human_approval": {
                    "reason": new_block.reason,
                    "confidence": 1.0,
                    "approved_at": _now(),
                    "automatic": False,
                    "added_block": True,
                }
            },
        )
        page.blocks.append(block)
        atomic_write_json(path / "pages" / f"{page_number:04d}" / "canonical.json", page)
        atomic_write_json(document_path, document)
        return block.model_dump(mode="json")

    @app.post("/api/jobs/{job_id}/export")
    def export_job(job_id: str) -> dict[str, Any]:
        path = _job_path(runtime_settings, job_id)
        document_path = path / "document" / "canonical_document.json"
        if not document_path.is_file():
            raise HTTPException(status_code=409, detail="No canonical document is available")
        document = CanonicalDocument.model_validate_json(document_path.read_text(encoding="utf-8"))
        store = JobStore(jobs_root, job_id)
        outputs = _export_document(document, store)
        _save_status(store, outputs=outputs)
        return {name: f"/api/jobs/{job_id}/files/{relative}" for name, relative in outputs.items()}

    @app.get("/api/jobs/{job_id}/files/{relative_path:path}")
    def job_file(
        job_id: str,
        relative_path: str,
        download: bool = Query(False),
    ) -> FileResponse:
        job = _job_path(runtime_settings, job_id)
        target = (job / relative_path).resolve()
        if job not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="Job file not found")
        return FileResponse(
            target,
            filename=target.name if download else None,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    frontend = PROJECT_ROOT / "web" / "dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
