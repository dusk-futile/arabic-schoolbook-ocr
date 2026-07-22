from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader


class PdfRenderError(RuntimeError):
    pass


def pdf_page_count(path: Path) -> int:
    return len(PdfReader(path).pages)


def _ghostscript_executable() -> str | None:
    for name in ("gswin64c", "gswin32c", "gs"):
        executable = shutil.which(name)
        if executable:
            return executable
    fixed = Path("C:/Program Files/gs/gs10.04.0/bin/gswin64c.exe")
    return str(fixed) if fixed.is_file() else None


def render_pdf_pages(
    pdf_path: Path,
    output_dir: Path,
    pages: list[int],
    *,
    dpi: int = 300,
) -> list[Path]:
    """Render selected one-based pages locally with stable names."""

    total = pdf_page_count(pdf_path)
    invalid = [page for page in pages if page < 1 or page > total]
    if invalid:
        raise ValueError(f"Pages outside 1..{total}: {invalid}")
    output_dir.mkdir(parents=True, exist_ok=True)
    ghostscript = _ghostscript_executable()
    pdftoppm = shutil.which("pdftoppm")
    rendered: list[Path] = []
    for page in pages:
        destination = output_dir / f"page-{page:04d}.png"
        if ghostscript:
            subprocess.run(
                [
                    ghostscript,
                    "-dSAFER",
                    "-dBATCH",
                    "-dNOPAUSE",
                    "-sDEVICE=png16m",
                    f"-r{dpi}",
                    f"-dFirstPage={page}",
                    f"-dLastPage={page}",
                    f"-sOutputFile={destination}",
                    str(pdf_path),
                ],
                check=True,
                capture_output=True,
                timeout=180,
            )
        elif pdftoppm:
            prefix = output_dir / f"page-{page:04d}-render"
            subprocess.run(
                [
                    pdftoppm,
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                    "-r",
                    str(dpi),
                    "-singlefile",
                    "-png",
                    str(pdf_path),
                    str(prefix),
                ],
                check=True,
                capture_output=True,
                timeout=180,
            )
            prefix.with_suffix(".png").replace(destination)
        else:
            try:
                import pypdfium2 as pdfium

                document = pdfium.PdfDocument(str(pdf_path))
                try:
                    bitmap = document[page - 1].render(scale=dpi / 72)
                    bitmap.to_pil().save(destination, format="PNG")
                finally:
                    document.close()
            except (ImportError, OSError, RuntimeError) as exc:
                raise PdfRenderError(
                    "Ghostscript, pdftoppm, or the bundled pypdfium2 fallback is required "
                    "for local PDF rendering"
                ) from exc
        if not destination.is_file() or destination.stat().st_size == 0:
            raise PdfRenderError(f"Renderer did not create {destination}")
        rendered.append(destination)
    return rendered
