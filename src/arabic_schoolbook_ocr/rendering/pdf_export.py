from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class DocxPdfExportError(RuntimeError):
    pass


def _export_with_word(docx_path: Path, output_path: Path) -> Path:
    try:
        import win32com.client
    except ImportError as exc:
        raise DocxPdfExportError("Microsoft Word is installed but pywin32 is unavailable") from exc
    word = None
    document = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        word.AutomationSecurity = 3
        document = word.Documents.Open(
            str(docx_path.resolve()),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
        )
        document.ExportAsFixedFormat(
            OutputFileName=str(output_path.resolve()),
            ExportFormat=17,
            OpenAfterExport=False,
            OptimizeFor=0,
            Range=0,
            Item=0,
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=0,
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )
    except Exception as exc:
        raise DocxPdfExportError(f"Microsoft Word PDF conversion failed: {exc}") from exc
    finally:
        if document is not None:
            document.Close(False)
        if word is not None:
            word.Quit()
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise DocxPdfExportError("Microsoft Word did not create the requested PDF")
    return output_path


def export_docx_to_pdf(docx_path: Path, output_path: Path) -> Path:
    """Render DOCX with a locally installed LibreOffice; never uses a cloud converter."""

    if not docx_path.is_file():
        raise FileNotFoundError(docx_path)
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    if executable is None:
        if sys.platform == "win32":
            return _export_with_word(docx_path, output_path)
        raise DocxPdfExportError(
            "LibreOffice was not found. Install it locally to enable rendered-PDF validation."
        )
    completed = subprocess.run(
        [
            executable,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_path.parent),
            str(docx_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    generated = output_path.parent / f"{docx_path.stem}.pdf"
    if completed.returncode != 0 or not generated.is_file():
        message = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise DocxPdfExportError(f"LibreOffice conversion failed: {message}")
    if generated.resolve() != output_path.resolve():
        generated.replace(output_path)
    return output_path
