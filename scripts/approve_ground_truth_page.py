from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from arabic_schoolbook_ocr.ground_truth import GroundTruthManifest
from arabic_schoolbook_ocr.persistence import atomic_write_json
from arabic_schoolbook_ocr.schemas import BlockType, CanonicalDocument


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Explicitly approve one fully reviewed private ground-truth page"
    )
    result.add_argument("manifest", type=Path)
    result.add_argument("job", type=Path)
    result.add_argument("page", type=int)
    result.add_argument("--reviewer", required=True)
    return result


def main() -> None:
    arguments = parser().parse_args()
    manifest_path = arguments.manifest.resolve()
    manifest = GroundTruthManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.training_allowed or manifest.classification != "EVALUATION_ONLY":
        raise SystemExit("Ground-truth approval refused: evaluation-only invariant changed")
    document_path = arguments.job.resolve() / "document" / "canonical_document.json"
    document = CanonicalDocument.model_validate_json(document_path.read_text(encoding="utf-8"))
    if document.source_sha256 != manifest.source_sha256:
        raise SystemExit("Ground-truth approval refused: source hash mismatch")
    reviewed_page = next(
        (page for page in document.pages if page.page_number == arguments.page), None
    )
    target = next((page for page in manifest.pages if page.page_number == arguments.page), None)
    if reviewed_page is None or target is None:
        raise SystemExit("Page is not present in both the job and benchmark manifest")
    unapproved = [
        block.id
        for block in reviewed_page.blocks
        if block.block_type not in {BlockType.FIGURE, BlockType.DECORATIVE_REGION}
        and "human_approval" not in block.evidence
    ]
    if unapproved:
        raise SystemExit(
            "Every text/table block must be visually reviewed in the UI before page approval; "
            f"unapproved block IDs: {unapproved}"
        )
    target.approve(reviewed_page, arguments.reviewer)
    atomic_write_json(manifest_path, manifest)
    print(f"Approved ground-truth page {arguments.page} by {arguments.reviewer}")


if __name__ == "__main__":
    main()
