from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

from .adjudicators import DisabledAdjudicator, GeminiAdjudicator
from .config import Settings
from .gemini_agents import (
    GeminiDocumentFormattingAnalyst,
    GeminiRenderedWordVisualQa,
    GeminiVerificationPolicy,
    VerificationScope,
)
from .protocols import LayoutProvider, OcrProvider, VisualAdjudicator
from .providers import (
    AzureDocumentIntelligenceProvider,
    FullPageLayoutProvider,
    MockLayoutProvider,
    MockOcrProvider,
    PaddleLocalLayoutProvider,
    PaddleLocalOcrProvider,
    UnlimitedOcrProvider,
    WindowsOcrProvider,
)
from .providers.errors import ProviderUnavailableError


@dataclass(frozen=True)
class ProviderBundle:
    primary: OcrProvider
    layout: LayoutProvider
    verifier: OcrProvider | None
    adjudicator: VisualAdjudicator
    verification_policy: GeminiVerificationPolicy | None = None
    formatting_analyst: GeminiDocumentFormattingAnalyst | None = None
    visual_qa: GeminiRenderedWordVisualQa | None = None


def build_provider_bundle(
    mode: str,
    settings: Settings,
    *,
    project_root: Path,
    device: str = "cpu",
    verification_scope: str = "off",
    formatting_enabled: bool = False,
    visual_qa_enabled: bool = False,
) -> ProviderBundle:
    windows = (
        WindowsOcrProvider(project_root / "scripts" / "run_windows_ocr.ps1")
        if platform.system() == "Windows"
        else None
    )
    if mode == "windows":
        if windows is None:
            raise ProviderUnavailableError("Windows OCR mode is available only on Windows")
        return ProviderBundle(windows, FullPageLayoutProvider(), None, DisabledAdjudicator())
    if mode == "mock":
        return ProviderBundle(MockOcrProvider(), MockLayoutProvider(), None, DisabledAdjudicator())
    scope = VerificationScope(verification_scope)

    def gemini_components() -> tuple[
        VisualAdjudicator,
        GeminiVerificationPolicy | None,
        GeminiDocumentFormattingAnalyst | None,
        GeminiRenderedWordVisualQa | None,
    ]:
        adjudicator: VisualAdjudicator = (
            GeminiAdjudicator(settings) if scope != VerificationScope.OFF else DisabledAdjudicator()
        )
        policy = (
            GeminiVerificationPolicy(settings, scope) if scope != VerificationScope.OFF else None
        )
        formatter = GeminiDocumentFormattingAnalyst(settings) if formatting_enabled else None
        visual_qa = GeminiRenderedWordVisualQa(settings) if visual_qa_enabled else None
        return adjudicator, policy, formatter, visual_qa

    if mode == "local":
        if scope != VerificationScope.OFF or formatting_enabled or visual_qa_enabled:
            adjudicator, policy, formatter, visual_qa = gemini_components()
            return ProviderBundle(
                PaddleLocalOcrProvider(device=device),
                PaddleLocalLayoutProvider(device=device),
                windows,
                adjudicator,
                policy,
                formatter,
                visual_qa,
            )
        return ProviderBundle(
            PaddleLocalOcrProvider(device=device),
            PaddleLocalLayoutProvider(device=device),
            windows,
            DisabledAdjudicator(),
        )
    if mode == "ai_verified":
        adjudicator, policy, formatter, visual_qa = gemini_components()
        return ProviderBundle(
            PaddleLocalOcrProvider(device=device),
            PaddleLocalLayoutProvider(device=device),
            windows,
            adjudicator,
            policy,
            formatter,
            visual_qa,
        )
    if mode == "azure":
        return ProviderBundle(
            AzureDocumentIntelligenceProvider(settings),
            FullPageLayoutProvider(),
            None,
            DisabledAdjudicator(),
        )
    if mode == "hybrid":
        adjudicator, policy, formatter, visual_qa = gemini_components()
        return ProviderBundle(
            AzureDocumentIntelligenceProvider(settings),
            FullPageLayoutProvider(),
            PaddleLocalOcrProvider(device=device),
            adjudicator,
            policy,
            formatter,
            visual_qa,
        )
    if mode == "maximum_accuracy":
        adjudicator, policy, formatter, visual_qa = gemini_components()
        return ProviderBundle(
            AzureDocumentIntelligenceProvider(settings),
            FullPageLayoutProvider(),
            PaddleLocalOcrProvider(device=device),
            adjudicator,
            policy,
            formatter,
            visual_qa,
        )
    if mode == "unlimited":
        provider = UnlimitedOcrProvider(settings)
        preflight = provider.preflight()
        if not preflight.available:
            raise ProviderUnavailableError(preflight.reason)
        return ProviderBundle(
            provider,
            PaddleLocalLayoutProvider(device=device),
            windows,
            DisabledAdjudicator(),
        )
    raise ValueError(f"Unknown provider mode: {mode}")
