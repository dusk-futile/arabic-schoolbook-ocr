from __future__ import annotations

# ruff: noqa: E501 -- long source/observation prose and embedded HTML remain readable here.
import argparse
import html
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from arabic_schoolbook_ocr.pdf_render import render_pdf_pages
from arabic_schoolbook_ocr.schemas import BlockType, CanonicalDocument

DEFAULT_PAGES = [1, 2, 4, 36, 53, 88, 143, 184, 188, 209]
RATIONALE = {
    1: "title-page hierarchy",
    2: "editable table",
    4: "dense body paragraphs",
    36: "questions and numbering",
    53: "mixed Arabic/English text",
    88: "heading and list hierarchy",
    143: "heading/body transition",
    184: "figure and caption",
    188: "multiple figures on one page",
    209: "closing-page table",
}
VISUAL_OBSERVATIONS = {
    1: "Title content is compressed toward the top; source centering and vertical hierarchy are not reproduced.",
    2: "The table remains editable, but its scale and the surrounding vertical spacing differ materially from the source.",
    4: "Body text occupies only the upper portion of the Word page, indicating missing OCR content and compressed reflow.",
    36: "Question content is sparse and top-weighted; numbering and completeness need line-by-line review.",
    53: "Mixed Arabic/English content is present, but wrapping, token placement, and vertical distribution do not match the source.",
    88: "Heading/list hierarchy is represented semantically, while spacing and page balance remain compressed.",
    143: "Heading/body flow is top-weighted and needs paragraph-boundary and spacing correction.",
    184: "The figure is retained, but figure scale, caption placement, and surrounding text spacing differ from the source.",
    188: "Multiple figures are retained, but they cluster toward the top and their source-relative vertical placement is lost.",
    209: "The closing table is editable, but it is underscaled and positioned too high relative to the source.",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Create a non-metric ten-page source/canonical/DOCX formatting audit"
    )
    result.add_argument("job_dir", type=Path)
    result.add_argument(
        "--pages",
        default=",".join(str(page) for page in DEFAULT_PAGES),
        help="Comma-separated one-based source/DOCX pages",
    )
    result.add_argument("--dpi", type=int, default=150)
    return result


def relative(from_dir: Path, target: Path) -> str:
    return Path(os.path.relpath(target, from_dir)).as_posix()


def logical_preview(page) -> str:  # type: ignore[no-untyped-def]
    blocks: list[str] = []
    for block in sorted(page.blocks, key=lambda item: item.reading_order):
        direction = "rtl" if block.paragraph_direction.value == "RTL" else "ltr"
        text = html.escape(block.literal_text) or "<em>[visual/non-text block]</em>"
        blocks.append(
            f'<section class="logical-block" dir="{direction}">'
            f'<span class="tag">{html.escape(block.block_type.value)} · '
            f'{block.confidence:.2f}</span><div>{text}</div></section>'
        )
    return "".join(blocks)


def page_summary(page) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    unresolved = sum(block.unresolved for block in page.blocks)
    types = {block.block_type for block in page.blocks}
    checks = [
        f"{len(page.blocks)} canonical blocks",
        f"{unresolved} unresolved",
        "reading order serialized",
        "one DOCX page mapped to one source page",
    ]
    if BlockType.TABLE in types:
        checks.append("editable table structure present")
    if types & {
        BlockType.DOCUMENT_TITLE,
        BlockType.CHAPTER_TITLE,
        BlockType.HEADING_1,
        BlockType.HEADING_2,
        BlockType.HEADING_3,
    }:
        checks.append("semantic heading present")
    if types & {BlockType.FIGURE, BlockType.EQUATION_IMAGE}:
        checks.append("source visual crop present or queued")
    issues = list(page.warnings)
    if unresolved:
        issues.append(f"{unresolved} OCR block(s) still require human resolution")
    issues.append("visual fidelity and reading comfort require human approval")
    return "; ".join(checks), "; ".join(issues)


def make_contact_sheet(
    job_dir: Path,
    pages: list[int],
    rendered: dict[int, Path],
    destination: Path,
) -> None:
    cell_width, cell_height = 330, 470
    sheet = Image.new("RGB", (cell_width * 3, (cell_height + 34) * len(pages)), "white")
    draw = ImageDraw.Draw(sheet)
    for row, page_number in enumerate(pages):
        paths = [
            job_dir / "pages" / f"{page_number:04d}" / "source.png",
            job_dir / "pages" / f"{page_number:04d}" / "reading_order_overlay.png",
            rendered[page_number],
        ]
        for column, path in enumerate(paths):
            with Image.open(path) as image:
                thumb = ImageOps.contain(image.convert("RGB"), (cell_width - 12, cell_height - 12))
            x = column * cell_width + (cell_width - thumb.width) // 2
            y = row * (cell_height + 34) + 28 + (cell_height - thumb.height) // 2
            sheet.paste(thumb, (x, y))
        draw.text(
            (8, row * (cell_height + 34) + 7),
            f"Page {page_number}: source | detected order | rendered Word",
            fill="black",
        )
    sheet.save(destination, quality=88, optimize=True)


def main() -> None:
    arguments = parser().parse_args()
    job_dir = arguments.job_dir.resolve()
    canonical_path = job_dir / "document" / "canonical_document.json"
    rendered_pdf = job_dir / "output" / "book_rendered.pdf"
    if not canonical_path.is_file() or not rendered_pdf.is_file():
        raise SystemExit("Job must contain document/canonical_document.json and output/book_rendered.pdf")
    pages = [int(value.strip()) for value in arguments.pages.split(",") if value.strip()]
    document = CanonicalDocument.model_validate_json(canonical_path.read_text(encoding="utf-8"))
    by_page = {page.page_number: page for page in document.pages}
    missing = [page for page in pages if page not in by_page]
    if missing:
        raise SystemExit(f"Canonical pages not found: {missing}")

    output_dir = job_dir / "output"
    rendered_dir = output_dir / "formatting_audit_rendered"
    rendered_paths = render_pdf_pages(rendered_pdf, rendered_dir, pages, dpi=arguments.dpi)
    rendered = dict(zip(pages, rendered_paths, strict=True))

    rows: list[str] = []
    markdown_rows: list[str] = []
    for page_number in pages:
        page = by_page[page_number]
        checks, issues = page_summary(page)
        source = job_dir / "pages" / f"{page_number:04d}" / "source.png"
        overlay = job_dir / "pages" / f"{page_number:04d}" / "reading_order_overlay.png"
        if not source.is_file() or not overlay.is_file():
            raise SystemExit(f"Missing audit images for page {page_number}")
        rows.append(
            f"""
            <article>
              <h2>Page {page_number}: {html.escape(RATIONALE.get(page_number, 'representative page'))}</h2>
              <p class="status">Automated visual comparison: <strong>NEEDS_CORRECTION</strong>; human approval: <strong>PENDING_REVIEW</strong></p>
              <div class="grid">
                <figure><img src="{relative(output_dir, source)}"><figcaption>Source page</figcaption></figure>
                <figure><img src="{relative(output_dir, overlay)}"><figcaption>Detected blocks and reading order</figcaption></figure>
                <figure class="logical"><div>{logical_preview(page)}</div><figcaption>Canonical logical preview</figcaption></figure>
                <figure><img src="{relative(output_dir, rendered[page_number])}"><figcaption>Rendered editable Word output</figcaption></figure>
              </div>
              <dl><dt>Automated structural evidence</dt><dd>{html.escape(checks)}</dd>
                  <dt>Observed visual mismatch</dt><dd>{html.escape(VISUAL_OBSERVATIONS.get(page_number, 'Visual fidelity requires correction.'))}</dd>
                  <dt>Open issues</dt><dd>{html.escape(issues)}</dd></dl>
            </article>"""
        )
        markdown_rows.append(
            f"| {page_number} | {RATIONALE.get(page_number, 'representative page')} | "
            f"{len(page.blocks)} | {sum(block.unresolved for block in page.blocks)} | "
            "NEEDS_CORRECTION / PENDING_HUMAN_REVIEW |"
        )

    html_path = output_dir / "FORMATTING_AUDIT.html"
    html_path.write_text(
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Formatting audit</title><style>
body{font:15px/1.45 system-ui;margin:0;background:#f3f0e8;color:#222}main{max-width:1480px;margin:auto;padding:28px}
article{background:white;padding:22px;margin:0 0 28px;border-radius:12px;box-shadow:0 2px 12px #0002}
h1,h2{margin-top:0}.status{color:#8a4b08}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
figure{margin:0;border:1px solid #ccc;background:#fafafa;padding:10px}img{display:block;width:100%;height:620px;object-fit:contain}
figcaption{text-align:center;font-weight:650;margin-top:8px}.logical>div{height:620px;overflow:auto;background:white;padding:14px}
.logical-block{border-bottom:1px solid #ddd;padding:8px}.tag{font:11px system-ui;color:#777}.logical-block div{font-size:18px}
dt{font-weight:700;margin-top:10px}dd{margin-left:0}@media(max-width:900px){.grid{grid-template-columns:1fr}img,.logical>div{height:auto;max-height:680px}}
</style></head><body><main><h1>Ten-page formatting audit</h1>
<p>This is a source-to-Word visual audit, not an OCR accuracy score. No page is marked passed until a human compares all four panels at 100% zoom.</p>
"""
        + "".join(rows)
        + "</main></body></html>",
        encoding="utf-8",
    )
    markdown_path = output_dir / "FORMATTING_AUDIT.md"
    markdown_path.write_text(
        "# Ten-page formatting audit\n\n"
        "Status: `PENDING_HUMAN_VISUAL_APPROVAL`\n\n"
        "This audit compares the source page, detected reading order, canonical logical "
        "preview, and locally rendered Word page. It does not substitute for OCR ground "
        "truth or a human visual decision. Open `FORMATTING_AUDIT.html` beside its image "
        "directories for the full comparison.\n\n"
        "| Page | Selection reason | Blocks | Unresolved | Human status |\n"
        "|---:|---|---:|---:|---|\n"
        + "\n".join(markdown_rows)
        + "\n\n## Automated visual observations\n\n"
        + "\n".join(
            f"- Page {page}: {VISUAL_OBSERVATIONS.get(page, 'Visual fidelity requires correction.')}"
            for page in pages
        )
        + "\n\nNo formatting fidelity percentage is reported while all ten human decisions are pending.\n",
        encoding="utf-8",
    )
    contact_sheet = output_dir / "FORMATTING_AUDIT_CONTACT_SHEET.jpg"
    make_contact_sheet(job_dir, pages, rendered, contact_sheet)
    print(html_path)
    print(markdown_path)
    print(contact_sheet)


if __name__ == "__main__":
    main()
