from datetime import UTC, datetime

import pytest

from arabic_schoolbook_ocr.privacy import CloudConsentError, require_cloud_consent
from arabic_schoolbook_ocr.schemas import CloudConsent, PageContext


def context(consent: CloudConsent) -> PageContext:
    return PageContext(
        job_id="test",
        page_number=2,
        total_pages=5,
        source_sha256="0" * 64,
        consent=consent,
    )


def test_cloud_is_fail_closed() -> None:
    with pytest.raises(CloudConsentError):
        require_cloud_consent("azure", context(CloudConsent()))


def test_provider_and_page_scope_are_enforced() -> None:
    consent = CloudConsent(
        cloud_opt_in=True,
        allowed_providers={"azure"},
        allowed_pages={1},
        acknowledged_at=datetime.now(UTC),
    )
    with pytest.raises(CloudConsentError):
        require_cloud_consent("gemini", context(consent))
    with pytest.raises(CloudConsentError):
        require_cloud_consent("azure", context(consent))
