from __future__ import annotations

import html
import json
from pathlib import Path

from .schemas import CanonicalDocument, CorrectionRecord


def collect_corrections(document: CanonicalDocument) -> list[CorrectionRecord]:
    corrections: list[CorrectionRecord] = []
    for page in document.pages:
        for block in page.blocks:
            corrected = block.approved_corrected_text
            if corrected is None or corrected == block.literal_text:
                continue
            automatic_approval = block.evidence.get("automatic_correction", {})
            human_approval = block.evidence.get("human_approval", {})
            approval = human_approval or automatic_approval
            automatic = bool(automatic_approval) and not bool(human_approval)
            corrections.append(
                CorrectionRecord(
                    page=page.page_number,
                    block_id=block.id,
                    source_crop=block.source_crop,
                    literal=block.literal_text,
                    corrected=corrected,
                    reason=str(approval.get("reason", "Approved correction")),
                    confidence=float(approval.get("confidence", 1.0)),
                    automatic=automatic,
                )
            )
    return corrections


def write_correction_reports(document: CanonicalDocument, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = collect_corrections(document)
    json_path = output_dir / "correction_report.json"
    json_path.write_text(
        json.dumps(
            [record.model_dump(mode="json") for record in records], ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    rows = "".join(
        "<tr>"
        f"<td>{record.page}</td>"
        f"<td dir='rtl'>{html.escape(record.literal)}</td>"
        f"<td dir='rtl'>{html.escape(record.corrected)}</td>"
        f"<td>{html.escape(record.reason)}</td>"
        f"<td>{record.confidence:.3f}</td>"
        f"<td>{'AI visual evidence' if record.automatic else 'Human'}</td>"
        "</tr>"
        for record in records
    )
    html_path = output_dir / "correction_report.html"
    correction_css = (
        "<style>body{font:15px Arial;margin:2rem;color:#172033}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #d7dee8;padding:.65rem;vertical-align:top}"
        "th{background:#eef6f5}</style>"
    )
    html_path.write_text(
        "<!doctype html><meta charset='utf-8'><title>Correction report</title>"
        + correction_css
        + "<h1>Correction report</h1>"
        + f"<p>{len(records)} approved changes. Automatic changes require crop-level visual "
        + "evidence, the configured confidence threshold, and no protected-content flag.</p>"
        + "<table><thead><tr><th>Page</th><th>Literal</th><th>Corrected</th>"
        + "<th>Reason</th><th>Confidence</th><th>Approval source</th></tr></thead>"
        + f"<tbody>{rows}</tbody></table>",
        encoding="utf-8",
    )
    return json_path, html_path


def write_smoke_report(document: CanonicalDocument, job_root: Path, output_path: Path) -> Path:
    return write_review_report(
        document,
        job_root,
        output_path,
        title="Five-page OCR smoke test",
    )


def write_review_report(
    document: CanonicalDocument,
    job_root: Path,
    output_path: Path,
    *,
    title: str = "OCR review report",
) -> Path:
    panels: list[str] = []
    for page in sorted(document.pages, key=lambda item: item.page_number):
        blocks = "".join(
            f"<li><strong>{html.escape(block.block_type.value)}</strong> "
            f"<span>{block.confidence:.3f}</span><pre dir='rtl'>"
            f"{html.escape(block.literal_text)}</pre></li>"
            for block in sorted(page.blocks, key=lambda item: item.reading_order)
        )
        source = Path(page.source_image).as_posix()
        preprocessed = Path(page.preprocessed_image or "").as_posix()
        page_root = Path("pages") / f"{page.page_number:04d}"
        layout_overlay = (page_root / "layout_overlay.png").as_posix()
        reading_overlay = (page_root / "reading_order_overlay.png").as_posix()
        evidence_links = "".join(
            f"<a href='../{(page_root / name).as_posix()}'>{html.escape(label)}</a>"
            for name, label in (
                ("ocr.json", "primary JSON"),
                ("verifier.json", "verifier JSON"),
                ("canonical.json", "canonical JSON"),
            )
            if (job_root / page_root / name).is_file()
        )
        panels.append(
            f"<section><h2>Page {page.page_number} - {html.escape(page.status.value)}</h2>"
            "<div class='comparison'>"
            f"<figure><img src='../{source}'><figcaption>Source</figcaption></figure>"
            f"<figure><img src='../{preprocessed}'><figcaption>Preprocessed</figcaption></figure>"
            f"<figure><img src='../{layout_overlay}'><figcaption>Layout</figcaption></figure>"
            f"<figure><img src='../{reading_overlay}'>"
            "<figcaption>Reading order</figcaption></figure>"
            f"<article><ol>{blocks}</ol></article></div>"
            f"<p class='links'>{evidence_links}</p>"
            f"<p>Warnings: {html.escape('; '.join(page.warnings) or 'none')}</p>"
            f"<p>Timing: {html.escape(json.dumps(page.timings_ms))}</p></section>"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    smoke_css = (
        "<style>body{font:14px Arial;margin:0;color:#172033;background:#f6f8fb}"
        "header,section{padding:1.4rem 2rem}header{background:#083f47;color:white}"
        "section{background:white;margin:1rem;border:1px solid #d7dee8}"
        ".comparison{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}"
        "img{width:100%;max-height:720px;object-fit:contain}"
        "pre{white-space:pre-wrap;font:16px Arial}li{margin-bottom:1rem}"
        ".links{display:flex;gap:1rem;flex-wrap:wrap}a{color:#08747b}"
        "@media(max-width:900px){.comparison{grid-template-columns:1fr}}</style>"
    )
    output_path.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        + smoke_css
        + f"</head><body><header><h1>{html.escape(title)}</h1>"
        + "<p>Accuracy remains unmeasured until human ground truth is complete.</p></header>"
        + "".join(panels)
        + "</body></html>",
        encoding="utf-8",
    )
    return output_path


def write_pending_accuracy_report(
    output_path: Path,
    *,
    benchmark_pages: list[int],
    modes: list[str],
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(mode)}</td>"
        "<td>UNMEASURED_PENDING_HUMAN_GROUND_TRUTH</td>"
        "<td>Not computed</td>"
        "</tr>"
        for mode in modes
    )
    output_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Accuracy report</title>"
        "<style>body{font:15px Arial;margin:2rem;color:#172033;max-width:1100px}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #d7dee8;"
        "padding:.65rem}th{background:#eef6f5}</style></head><body>"
        "<h1>Accuracy report</h1>"
        "<p><strong>Accuracy is not yet measured.</strong> Draft OCR output is not ground "
        "truth. CER, WER, and all derived accuracy metrics remain blocked until every "
        "selected page is fully corrected and approved by a human reviewer.</p>"
        f"<p>Private benchmark pages: {html.escape(', '.join(map(str, benchmark_pages)))}</p>"
        "<table><thead><tr><th>Mode</th><th>Status</th><th>Metrics</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></body></html>",
        encoding="utf-8",
    )
    return output_path
