from __future__ import annotations

from PIL.Image import Image

from .gemini_agents import GeminiVisualOcrVerifier
from .schemas import AdjudicationContext, AdjudicationResult, OcrCandidate


class DisabledAdjudicator:
    name = "disabled"

    def adjudicate(
        self,
        crop: Image,
        candidates: list[OcrCandidate],
        context: AdjudicationContext,
    ) -> AdjudicationResult:
        return AdjudicationResult(provider=self.name, rationale="Visual adjudication disabled")


class MockAdjudicator:
    name = "mock-adjudicator"

    def adjudicate(
        self,
        crop: Image,
        candidates: list[OcrCandidate],
        context: AdjudicationContext,
    ) -> AdjudicationResult:
        if not candidates:
            return AdjudicationResult(provider=self.name, rationale="No candidates")
        choice = max(candidates, key=lambda candidate: candidate.confidence)
        return AdjudicationResult(
            provider=self.name,
            selected_text=choice.text,
            confidence=choice.confidence,
            rationale="Selected highest-confidence mock candidate",
            unresolved=False,
        )


# Backward-compatible name used by runtime construction.
GeminiAdjudicator = GeminiVisualOcrVerifier

__all__ = [
    "DisabledAdjudicator",
    "GeminiAdjudicator",
    "GeminiVisualOcrVerifier",
    "MockAdjudicator",
]
