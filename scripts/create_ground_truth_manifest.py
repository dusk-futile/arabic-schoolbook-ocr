from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from arabic_schoolbook_ocr.ground_truth import (
    DEFAULT_BENCHMARK_PAGES,
    GroundTruthManifest,
    GroundTruthPage,
)
from arabic_schoolbook_ocr.persistence import atomic_write_json
from arabic_schoolbook_ocr.schemas import CanonicalDocument


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Create a private, unreviewed 30-page ground-truth draft"
    )
    result.add_argument("job", type=Path, help="Full-book job directory")
    result.add_argument("--output", type=Path)
    return result


def main() -> None:
    arguments = parser().parse_args()
    job = arguments.job.resolve()
    canonical_path = job / "document" / "canonical_document.json"
    if not canonical_path.is_file():
        raise SystemExit(f"Canonical document not found: {canonical_path}")
    document = CanonicalDocument.model_validate_json(canonical_path.read_text(encoding="utf-8"))
    if document.classification != "EVALUATION_ONLY":
        raise SystemExit("Private benchmark creation requires EVALUATION_ONLY classification")
    pages_by_number = {page.page_number: page for page in document.pages}
    missing = [number for number, _ in DEFAULT_BENCHMARK_PAGES if number not in pages_by_number]
    if missing:
        raise SystemExit(f"Full-book canonical document is missing benchmark pages: {missing}")
    output = arguments.output or (
        ROOT / "data" / "ground_truth" / job.name / "ground_truth_manifest.json"
    )
    manifest = GroundTruthManifest(
        source_sha256=document.source_sha256,
        classification="EVALUATION_ONLY",
        training_allowed=False,
        pages=[
            GroundTruthPage(
                page_number=page_number,
                category=category,
                source_image=str(job / pages_by_number[page_number].source_image),
                draft=pages_by_number[page_number],
                human_reviewed=False,
            )
            for page_number, category in DEFAULT_BENCHMARK_PAGES
        ],
    )
    atomic_write_json(output, manifest)
    status_path = output.with_name("README.md")
    status_path.write_text(
        "# Private ground-truth draft\n\n"
        "This directory is ignored by Git. All pages are EVALUATION_ONLY and "
        "`training_allowed` is false. Category labels are provisional until a human "
        "visually confirms the selected pages. Draft OCR is not ground truth.\n\n"
        "Metrics are blocked until all 30 pages have exact text, boxes, block types, "
        "reading order, paragraph groups, boundary labels, mixed-script runs, and table "
        "cells corrected and each page is explicitly marked `human_reviewed=true`.\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
