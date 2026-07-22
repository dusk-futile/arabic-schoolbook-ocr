from __future__ import annotations

from .schemas import AdjudicationContext, PageContext


class CloudConsentError(PermissionError):
    """Raised before bytes are serialized or sent to a cloud provider."""


def require_cloud_consent(provider: str, context: PageContext) -> None:
    consent = context.consent
    if not consent.cloud_opt_in:
        raise CloudConsentError(f"Cloud provider {provider!r} requires explicit job opt-in")
    if provider not in consent.allowed_providers:
        raise CloudConsentError(f"Cloud provider {provider!r} is not allowed for this job")
    if consent.allowed_pages is not None and context.page_number not in consent.allowed_pages:
        raise CloudConsentError(
            f"Page {context.page_number} was not included in the cloud-consent scope"
        )


def require_gemini_crop_consent(context: AdjudicationContext) -> None:
    require_cloud_consent("gemini", context.page)
    if context.full_page_crop and not context.page.consent.allow_full_document_gemini:
        raise CloudConsentError(
            "Full-page Gemini input requires the separate full-document Gemini confirmation"
        )
