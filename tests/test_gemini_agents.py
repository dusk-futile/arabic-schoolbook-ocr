import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import SecretStr, ValidationError

from arabic_schoolbook_ocr.config import Settings
from arabic_schoolbook_ocr.gemini_agents import (
    FormattingAnalysisResult,
    GeminiDocumentFormattingAnalyst,
    GeminiRenderedWordVisualQa,
    GeminiStructuredClient,
    GeminiVerificationPolicy,
    GeminiVisualOcrVerifier,
    RenderedWordVisualQaResult,
    VerificationScope,
    apply_formatting_analysis,
)
from arabic_schoolbook_ocr.privacy import CloudConsentError
from arabic_schoolbook_ocr.schemas import (
    AdjudicationContext,
    BlockType,
    BoundingBox,
    CanonicalBlock,
    CanonicalPage,
    CloudConsent,
    OcrCandidate,
    PageContext,
)


class FakeInteractions:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        return SimpleNamespace(
            output_text=output,
            usage=SimpleNamespace(input_tokens=120, output_tokens=30),
        )


class FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.interactions = FakeInteractions(outputs)


def settings(**overrides) -> Settings:
    values = {
        "gemini_api_key": SecretStr("test-key-never-log"),
        "enable_gemini_verification": True,
        "enable_gemini_formatting": True,
        "enable_gemini_visual_qa": True,
        "gemini_max_retries": 2,
    }
    values.update(overrides)
    return Settings(**values)


def page_context(*, full_page: bool = False) -> PageContext:
    return PageContext(
        job_id="fixture",
        page_number=18,
        total_pages=30,
        source_sha256="0" * 64,
        consent=CloudConsent(
            cloud_opt_in=True,
            allowed_providers={"gemini"},
            allowed_pages={18},
            allow_full_document_gemini=full_page,
            acknowledged_at=datetime.now(UTC),
        ),
    )


def canonical_page() -> CanonicalPage:
    return CanonicalPage(
        page_number=18,
        width=1000,
        height=1400,
        source_image="pages/0018/source.png",
        blocks=[
            CanonicalBlock(
                id="b1",
                block_type=BlockType.BODY_PARAGRAPH,
                bbox=BoundingBox(x=100, y=100, width=800, height=300),
                reading_order=0,
                literal_text="النص الحرفي 25 m/s",
                unicode_normalized_text="النص الحرفي 25 m/s",
                line_ids=["l1", "l2"],
                confidence=0.7,
                unresolved=True,
            )
        ],
    )


def structured_client(
    configuration: Settings, outputs: list[str]
) -> tuple[GeminiStructuredClient, FakeClient]:
    fake = FakeClient(outputs)
    return (
        GeminiStructuredClient(configuration, client=fake, sleep=lambda _: None),
        fake,
    )


def test_verifier_uses_crop_and_validated_json_with_retry() -> None:
    configuration = settings()
    response = {
        "literal_text": "النص المرئي",
        "decision": "NEW_TRANSCRIPTION",
        "confidence": 0.97,
        "unresolved": False,
        "uncertain_spans": [],
        "visual_evidence": "The final glyphs are visible.",
        "content_changed": True,
    }
    client, fake = structured_client(configuration, ["not-json", json.dumps(response)])
    verifier = GeminiVisualOcrVerifier(configuration, client=client)
    result = verifier.adjudicate(
        Image.new("RGB", (40, 20), "white"),
        [OcrCandidate(text="النص", confidence=0.6, provider="primary")],
        AdjudicationContext(
            page=page_context(),
            block_id="b1",
            reason="low-confidence",
            crop_bbox=BoundingBox(x=0, y=0, width=40, height=20),
            region_type=BlockType.BODY_PARAGRAPH,
        ),
    )

    assert result.selected_text == "النص المرئي"
    assert result.decision == "NEW_TRANSCRIPTION"
    assert result.usage and result.usage.api_calls == 1
    assert len(fake.interactions.calls) == 2
    assert any(item["type"] == "image" for item in fake.interactions.calls[-1]["input"])


def test_verifier_checks_consent_before_serializing_or_calling() -> None:
    configuration = settings()
    client, fake = structured_client(configuration, [])
    verifier = GeminiVisualOcrVerifier(configuration, client=client)
    context = page_context()
    context.consent.cloud_opt_in = False

    with pytest.raises(CloudConsentError):
        verifier.adjudicate(
            Image.new("RGB", (20, 20), "white"),
            [],
            AdjudicationContext(
                page=context,
                block_id="b1",
                reason="test",
                crop_bbox=BoundingBox(x=0, y=0, width=20, height=20),
            ),
        )

    assert fake.interactions.calls == []


def test_formatter_schema_cannot_modify_verified_text() -> None:
    configuration = settings()
    response = {
        "page_number": 18,
        "reading_order": ["b1"],
        "blocks": [
            {
                "block_id": "b1",
                "type": "HEADING_1",
                "direction": "RTL",
                "alignment": "CENTER",
                "bold": True,
                "font_size_class": "LARGE",
                "space_before_pt": 12,
                "space_after_pt": 8,
                "keep_with_next": True,
                "line_boundaries": [
                    {"after_line": "l1", "class": "NEW_PARAGRAPH", "confidence": 0.91}
                ],
            }
        ],
        "warnings": [],
    }
    client, _ = structured_client(configuration, [json.dumps(response)])
    formatter = GeminiDocumentFormattingAnalyst(configuration, client=client)
    page = canonical_page()
    before = page.blocks[0].literal_text

    result = formatter.analyze(
        Image.new("RGB", (1000, 1400), "white"),
        page,
        page_context(full_page=True),
    )
    apply_formatting_analysis(page, result.result)

    assert page.blocks[0].literal_text == before
    assert page.blocks[0].block_type == BlockType.HEADING_1
    assert page.blocks[0].formatting and page.blocks[0].formatting.bold is True
    with pytest.raises(ValidationError):
        FormattingAnalysisResult.model_validate(
            {**response, "blocks": [{**response["blocks"][0], "replacement_text": "forbidden"}]}
        )


def test_rendered_word_qa_reports_seeded_missing_block_but_cannot_modify_docx() -> None:
    configuration = settings()
    response = {
        "page_passed": False,
        "issues": [
            {
                "type": "MISSING_BLOCK",
                "source_block_id": "b8",
                "severity": "HIGH",
                "description": "The seeded caption is absent.",
            }
        ],
        "recommended_actions": [{"action": "REBUILD_BLOCK", "block_id": "b8"}],
    }
    client, _ = structured_client(configuration, [json.dumps(response)])
    qa = GeminiRenderedWordVisualQa(configuration, client=client)
    result = qa.evaluate(
        Image.new("RGB", (1000, 1400), "white"),
        Image.new("RGB", (1000, 1400), "white"),
        canonical_page(),
        page_context(full_page=True),
    )

    assert result.result.page_passed is False
    assert result.result.issues[0].type.value == "MISSING_BLOCK"
    with pytest.raises(ValidationError):
        RenderedWordVisualQaResult.model_validate({**response, "modified_docx": "forbidden"})


def test_trigger_policy_uses_real_risk_signals_without_lowering_threshold() -> None:
    block = canonical_page().blocks[0]
    policy = GeminiVerificationPolicy(settings(), VerificationScope.IMPORTANT)
    reasons = policy.reasons(block, None)

    assert "low-confidence" in reasons
    assert "English" in reasons
    assert "digits-or-percentage" in reasons
    assert GeminiVerificationPolicy(settings(), VerificationScope.OFF).reasons(block, None) == []


def test_every_scope_excludes_non_text_regions() -> None:
    block = canonical_page().blocks[0].model_copy(
        update={"block_type": BlockType.FIGURE, "literal_text": ""}
    )
    policy = GeminiVerificationPolicy(settings(), VerificationScope.EVERY)

    assert policy.reasons(block, None) == []
