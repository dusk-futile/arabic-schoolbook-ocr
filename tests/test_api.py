from pathlib import Path

from fastapi.testclient import TestClient

from arabic_schoolbook_ocr.api import create_app
from arabic_schoolbook_ocr.config import Settings
from arabic_schoolbook_ocr.persistence import JobStore
from arabic_schoolbook_ocr.schemas import (
    BlockType,
    BoundingBox,
    CanonicalBlock,
    CanonicalDocument,
    CanonicalPage,
)


def _fixture_job(root: Path) -> tuple[JobStore, CanonicalDocument, CanonicalBlock]:
    store = JobStore(root, "fixture-job")
    store.initialize()
    block = CanonicalBlock(
        block_type=BlockType.BODY_PARAGRAPH,
        bbox=BoundingBox(x=10, y=20, width=300, height=80),
        reading_order=0,
        literal_text="النص الخام",
        unicode_normalized_text="النص الخام",
        confidence=0.6,
        unresolved=True,
    )
    page = CanonicalPage(
        page_number=1,
        width=1000,
        height=1400,
        source_image="pages/0001/source.png",
        blocks=[block],
    )
    document = CanonicalDocument(
        title="Fixture",
        source_filename="fixture.pdf",
        source_sha256="0" * 64,
        classification="EVALUATION_ONLY",
        pages=[page],
    )
    store.save_json("document/canonical_document.json", document)
    store.save_json("pages/0001/canonical.json", page)
    (store.page_dir(1) / "source.png").write_bytes(b"fixture")
    return store, document, block


def test_health_reports_training_disabled(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(job_root=tmp_path)))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["training"] == "disabled"


def test_block_correction_requires_and_records_human_approval(tmp_path: Path) -> None:
    _, _, block = _fixture_job(tmp_path)
    client = TestClient(create_app(Settings(job_root=tmp_path)))
    endpoint = f"/api/jobs/fixture-job/pages/1/blocks/{block.id}"

    denied = client.patch(endpoint, json={"approved_corrected_text": "النص المصحح"})
    accepted = client.patch(
        endpoint,
        json={
            "approved_corrected_text": "النص المصحح",
            "human_approved": True,
            "reason": "Compared with page image",
            "bbox": {"x": 12, "y": 22, "width": 290, "height": 78},
            "paragraph_group_id": "page-1-paragraph-1",
            "runs": [{"text": "النص المصحح", "script": "ARABIC", "direction": "RTL"}],
            "boundaries": [],
        },
    )

    assert denied.status_code == 422
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["literal_text"] == "النص الخام"
    assert payload["approved_corrected_text"] == "النص المصحح"
    assert payload["bbox"]["x"] == 12
    assert payload["paragraph_group_id"] == "page-1-paragraph-1"
    assert payload["runs"][0]["script"] == "ARABIC"
    assert payload["evidence"]["human_approval"]["automatic"] is False


def test_cloud_job_fails_closed_without_opt_in(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(job_root=tmp_path)))

    response = client.post(
        "/api/jobs",
        data={"mode": "azure", "cloud_opt_in": "false"},
        files={"file": ("sample.pdf", b"%PDF-invalid", "application/pdf")},
    )

    assert response.status_code == 403


def test_settings_accept_process_local_keys_without_echoing_or_persisting_them(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(Settings(job_root=tmp_path)))
    secret = "gemini-secret-value-must-not-appear"

    response = client.post(
        "/api/settings",
        json={
            "gemini_api_key": secret,
            "gemini_model": "gemini-3.6-flash",
            "enable_gemini_verification": True,
        },
    )
    providers = client.get("/api/providers")

    assert response.status_code == 200
    assert response.json()["gemini_key_configured"] is True
    assert response.json()["secrets_persisted"] is False
    assert secret not in response.text
    assert secret not in providers.text
    assert providers.json()["gemini"]["available"] is True


def test_gemini_job_requires_explicit_cloud_and_full_page_consent(tmp_path: Path) -> None:
    configuration = Settings(
        job_root=tmp_path,
        gemini_api_key="configured",
        enable_gemini_formatting=True,
    )
    client = TestClient(create_app(configuration))

    no_cloud = client.post(
        "/api/jobs",
        data={"mode": "local", "ai_formatting": "structural", "cloud_opt_in": "false"},
        files={"file": ("sample.pdf", b"%PDF-invalid", "application/pdf")},
    )
    no_full_page = client.post(
        "/api/jobs",
        data={
            "mode": "local",
            "ai_formatting": "structural",
            "cloud_opt_in": "true",
            "allow_full_page_gemini": "false",
        },
        files={"file": ("sample.pdf", b"%PDF-invalid", "application/pdf")},
    )

    assert no_cloud.status_code == 403
    assert no_full_page.status_code == 403
