from __future__ import annotations

import subprocess
from dataclasses import dataclass

from PIL.Image import Image

from ..config import Settings
from ..schemas import OcrPageResult, PageContext
from .errors import ProviderUnavailableError


@dataclass(frozen=True)
class UnlimitedPreflight:
    available: bool
    mode: str
    gpu_memory_mb: int | None
    reason: str


def detect_gpu_memory_mb() -> int | None:
    try:
        process = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    values = [int(line.strip()) for line in process.stdout.splitlines() if line.strip().isdigit()]
    return max(values) if values else None


class UnlimitedOcrProvider:
    """Optional research adapter; never blocks the production providers."""

    name = "unlimited-ocr-research"
    minimum_bf16_vram_mb = 8192

    def __init__(self, settings: Settings, *, quantized: bool = False) -> None:
        self.settings = settings
        self.quantized = quantized

    def preflight(self) -> UnlimitedPreflight:
        if self.settings.unlimited_ocr_remote_endpoint:
            return UnlimitedPreflight(
                False,
                "remote-stub",
                None,
                "Remote endpoint is configured, but its transport contract is not "
                "enabled in Phase 2",
            )
        memory = detect_gpu_memory_mb()
        if memory is None:
            return UnlimitedPreflight(False, "local", None, "No NVIDIA GPU was detected")
        if self.quantized:
            return UnlimitedPreflight(
                False,
                "local-quantized-experimental",
                memory,
                "Quantized loading is intentionally disabled until a compatible benchmark exists",
            )
        if memory < self.minimum_bf16_vram_mb:
            return UnlimitedPreflight(
                False,
                "local-bf16",
                memory,
                f"Official BF16 requires at least {self.minimum_bf16_vram_mb} MB VRAM",
            )
        return UnlimitedPreflight(
            False,
            "local-bf16",
            memory,
            "Hardware is sufficient, but local model loading is not enabled in Phase 2",
        )

    def process_page(self, page_image: Image, context: PageContext) -> OcrPageResult:
        preflight = self.preflight()
        raise ProviderUnavailableError(
            f"Unlimited-OCR is an optional research provider: {preflight.reason}"
        )
