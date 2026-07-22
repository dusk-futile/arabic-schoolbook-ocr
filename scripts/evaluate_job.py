from __future__ import annotations

import argparse
import html
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from arabic_schoolbook_ocr.ground_truth import GroundTruthManifest
from arabic_schoolbook_ocr.metrics import calculate_page_metrics
from arabic_schoolbook_ocr.persistence import atomic_write_json
from arabic_schoolbook_ocr.schemas import CanonicalDocument


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Evaluate one OCR job against fully human-reviewed ground truth"
    )
    result.add_argument("ground_truth", type=Path)
    result.add_argument("job", type=Path)
    result.add_argument("--output", type=Path)
    return result


def _aggregate(per_page: list[dict[str, Any]]) -> dict[str, float | int | None]:
    metric_names = sorted({name for page in per_page for name in page if name != "page"})
    result: dict[str, float | int | None] = {}
    count_metrics = {
        "missing_block_count",
        "hallucinated_block_count",
    }
    for name in metric_names:
        values = [page[name] for page in per_page if page.get(name) is not None]
        if not values:
            result[name] = None
        elif name in count_metrics:
            result[name] = sum(int(value) for value in values)
        else:
            result[name] = statistics.fmean(float(value) for value in values)
    return result


def _write_html(path: Path, report: dict[str, Any]) -> None:
    def display(value: Any) -> str:
        if value is None:
            return "N/A"
        return f"{value:.6f}" if isinstance(value, float) else str(value)

    rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{html.escape(display(value))}</td></tr>"
        for name, value in report["aggregate_metrics"].items()
    )
    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Measured accuracy</title>"
        "<style>body{font:15px Arial;margin:2rem;color:#172033;max-width:1000px}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #d7dee8;"
        "padding:.65rem}th{background:#eef6f5}</style></head><body>"
        "<h1>Measured accuracy</h1>"
        f"<p>Mode: {html.escape(report['mode'])}</p>"
        f"<p>Human-reviewed pages: {html.escape(', '.join(map(str, report['pages'])))}</p>"
        "<p>The private benchmark is EVALUATION_ONLY and was not used for training or "
        "validation.</p><table><thead><tr><th>Metric</th><th>Value</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></body></html>",
        encoding="utf-8",
    )


def main() -> None:
    arguments = parser().parse_args()
    manifest = GroundTruthManifest.model_validate_json(
        arguments.ground_truth.read_text(encoding="utf-8")
    )
    manifest.assert_ready_for_metrics()
    canonical_path = arguments.job / "document" / "canonical_document.json"
    document = CanonicalDocument.model_validate_json(canonical_path.read_text(encoding="utf-8"))
    if document.source_sha256 != manifest.source_sha256:
        raise SystemExit("Evaluation refused: hypothesis and ground-truth hashes differ")
    hypotheses = {page.page_number: page for page in document.pages}
    per_page: list[dict[str, Any]] = []
    for ground_truth_page in manifest.pages:
        hypothesis = hypotheses.get(ground_truth_page.page_number)
        if hypothesis is None or ground_truth_page.reviewed_page is None:
            raise SystemExit(f"Missing reviewed/hypothesis page {ground_truth_page.page_number}")
        metrics = calculate_page_metrics(
            ground_truth_page.reviewed_page,
            hypothesis,
            human_reviewed=ground_truth_page.human_reviewed,
        )
        per_page.append({"page": ground_truth_page.page_number, **metrics})
    usage = [usage for page in document.pages for usage in page.usage]
    report = {
        "status": "MEASURED_HUMAN_GROUND_TRUTH",
        "classification": manifest.classification,
        "training_allowed": manifest.training_allowed,
        "source_sha256": manifest.source_sha256,
        "mode": str(document.run_configuration.get("mode", "unknown")),
        "pages": [page.page_number for page in manifest.pages],
        "aggregate_metrics": _aggregate(per_page),
        "per_page": per_page,
        "latency_ms": {
            "total": sum(page.timings_ms.get("total", 0) for page in document.pages),
            "mean_per_page": statistics.fmean(
                page.timings_ms.get("total", 0) for page in document.pages
            ),
        },
        "api_usage": {
            "calls": sum(item.api_calls for item in usage),
            "pages_billed": sum(item.pages_billed for item in usage),
            "input_tokens": sum(item.input_tokens for item in usage),
            "output_tokens": sum(item.output_tokens for item in usage),
            "estimated_cost_usd": sum(item.estimated_cost or 0 for item in usage),
        },
    }
    output = arguments.output or arguments.job / "output" / "accuracy_report.json"
    atomic_write_json(output, report)
    _write_html(output.with_suffix(".html"), report)
    print(output)


if __name__ == "__main__":
    main()
