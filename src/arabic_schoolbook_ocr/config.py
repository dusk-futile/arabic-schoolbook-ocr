from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets are represented as SecretStr and never logged."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    training_approved: bool = False
    job_root: Path = Path("jobs")
    max_upload_mb: int = Field(default=500, ge=1, le=4096)

    azure_document_intelligence_endpoint: str | None = None
    azure_document_intelligence_key: SecretStr | None = None
    azure_document_intelligence_price_per_1000_pages: float | None = Field(default=None, ge=0)

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.6-flash"
    enable_gemini_verification: bool = False
    enable_gemini_formatting: bool = False
    enable_gemini_visual_qa: bool = False
    gemini_verify_confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    gemini_correction_confidence_threshold: float = Field(default=0.95, ge=0, le=1)
    gemini_verify_digits_always: bool = True
    gemini_verify_english_always: bool = True
    gemini_verify_headings_always: bool = True
    gemini_max_retries: int = Field(default=2, ge=0, le=8)
    gemini_max_parallel_requests: int = Field(default=4, ge=1, le=32)
    gemini_input_price_per_million_tokens: float | None = Field(default=None, ge=0)
    gemini_output_price_per_million_tokens: float | None = Field(default=None, ge=0)

    unlimited_ocr_remote_endpoint: str | None = None
    unlimited_ocr_remote_token: SecretStr | None = None

    def assert_training_disabled(self) -> None:
        if self.training_approved:
            raise RuntimeError(
                "This Phase 2 build has no authorized training path; set TRAINING_APPROVED=false."
            )
