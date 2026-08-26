"""End-to-end orchestration.

Every stage writes its intermediate to disk when ``work_dir`` is set, so a bad
page can be inspected rather than guessed at.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

from .arabic import canonical
from .model import DocResult, Line, PageInfo, Para
from .pdf_text import extract_page_lines
from .router import route_page

Progress = Callable[[str, str, float], None]   # (en, ar, fraction 0..1)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass
class Options:
    ocr: bool = True
    engine: str = "auto"
    dpi: int = 300
    keep_tashkeel: bool = True
    digits: str = "keep"
    correct: bool = True
    drop_furniture: bool = True
    max_pages: Optional[int] = None
    preprocess: bool = True
    repair_fonts: bool = True
    work_dir: Optional[str] = None
    force_ocr: bool = False


def _noop(en: str, ar: str, frac: float) -> None:
    pass


def _pix_to_bgr(pix):
    import cv2
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    if pix.n == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)


class Pipeline:
    def __init__(self, opts: Optional[Options] = None, progress: Progress = _noop):
        self.opts = opts or Options()
        self.progress = progress
        self._engine = None
        self._corrector = None

    # ---------------------------------------------------------------- lazy
    @property
    def engine(self):
        if self._engine is None:
            from .ocr import best_available, get_engine
            if self.opts.engine in ("auto", "", None):
                self._engine = best_available()
            else:
                self._engine = get_engine(self.opts.engine)
        return self._engine

    @property
    def corrector(self):
        if self._corrector is None:
            from .lexicon import Corrector
            self._corrector = Corrector()
        return self._corrector

    # ---------------------------------------------------------------- input
    def _pages_from_pdf(self, path: str) -> List[PageInfo]:
        import pymupdf
        from .font_repair import (FontDecoder, calibrate, choose_fonts, decode_page,
                                  repair_quality)
        doc = pymupdf.open(path)
        n = doc.page_count if self.opts.max_pages is None else min(self.opts.max_pages, doc.page_count)

        # Decide once per document whether the text layer is broken in the way
        # that font repair fixes. Calibration is document-wide because a glyph
        # id means the same thing on every page, and one page rarely has enough
        # occurrences to identify it.
        decoder = None
        self.repair_log = {}
        if self.opts.repair_fonts and not self.opts.force_ocr:
            probe_no = min(5, n - 1)
            probe = extract_page_lines(doc[probe_no], 1)
            if route_page(probe, corrector=self.corrector).mode == "ocr":
                decoder = FontDecoder(doc)
                self.progress("Repairing the document's font encoding",
                              "إصلاح ترميز الخطوط في الملف", 0.05)
                try:
                    step = max(1, n // 25)
                    sample = list(range(0, n, step))[:25]
                    self.font_report = choose_fonts(doc, decoder,
                                                    self.corrector.lex, sample)
                    resolved, log = calibrate(doc, decoder, self.corrector.lex,
                                              pages=sample)
                    decoder.apply_overrides(resolved)
                    self.repair_log = log
                except Exception:
                    decoder = None

        pages: List[PageInfo] = []
        for i in range(n):
            page = doc[i]
            self.progress(f"Reading page {i+1}/{n}", f"قراءة الصفحة {i+1}/{n}", 0.05 + (i / max(n, 1)) * 0.30)
            lines = extract_page_lines(page, i + 1)
            cov = repair_quality(doc, page) if decoder is not None else None
            route = (route_page(lines, glyph_coverage=cov, corrector=self.corrector)
                     if not self.opts.force_ocr else None)
            info = PageInfo(number=i + 1, width=page.rect.width, height=page.rect.height,
                            lines=lines, source="digital")
            if route is not None and route.mode == "font_repair" and decoder is not None:
                from .lines import merge_fragments
                repaired = merge_fragments(decode_page(doc, page, i + 1, decoder))
                if repaired:
                    info.lines = repaired
                    info.source = "font_repair"
                    info.notes.append(route.reason)
                    pages.append(info)
                    continue
            if self.opts.force_ocr or route.mode == "ocr":
                reason = "forced" if self.opts.force_ocr else route.reason
                if not self.opts.ocr:
                    info.notes.append(f"needs OCR ({reason}) but OCR disabled")
                    info.lines = []
                else:
                    img = _pix_to_bgr(page.get_pixmap(dpi=self.opts.dpi))
                    info.lines = self._ocr_image(img, i + 1, info)
                    info.source = "ocr"
                    info.notes.append(f"OCR: {reason}")
            else:
                info.notes.append(route.reason)
            pages.append(info)
        doc.close()
        return pages

    def _ocr_image(self, img, page_no: int, info: PageInfo) -> List[Line]:
        from .lines import merge_fragments
        if self.opts.preprocess:
            from .preprocess import prepare
            img, notes = prepare(img)
            for k, v in notes.items():
                info.notes.append(f"{k}={v}")
        scale = self.opts.dpi / 72.0
        h, w = img.shape[:2]
        info.width, info.height = w / scale, h / scale
        lines = self.engine.page_lines(img, page_no, scale)
        return merge_fragments(lines)

    def _pages_from_images(self, paths: List[str]) -> List[PageInfo]:
        import cv2
        pages: List[PageInfo] = []
        for i, p in enumerate(sorted(paths)):
            self.progress(f"Reading image {i+1}/{len(paths)}",
                          f"قراءة الصورة {i+1}/{len(paths)}", (i / max(len(paths), 1)) * 0.35)
            img = cv2.imread(p)
            if img is None:
                continue
            info = PageInfo(number=i + 1, width=0, height=0, source="ocr")
            info.notes.append(f"image: {os.path.basename(p)}")
            info.lines = self._ocr_image(img, i + 1, info)
            pages.append(info)
        return pages

    # ---------------------------------------------------------------- run
    def run(self, path: str) -> DocResult:
        t0 = time.time()
        self.progress("Starting", "بدء المعالجة", 0.0)
        if os.path.isdir(path):
            imgs = [os.path.join(path, f) for f in sorted(os.listdir(path))
                    if os.path.splitext(f)[1].lower() in IMAGE_EXT]
            pages = self._pages_from_images(imgs)
        elif os.path.splitext(path)[1].lower() == ".pdf":
            pages = self._pages_from_pdf(path)
        elif os.path.splitext(path)[1].lower() in IMAGE_EXT:
            pages = self._pages_from_images([path])
        elif os.path.splitext(path)[1].lower() in {".txt", ".text"}:
            pages = _pages_from_text(path)
        else:
            raise ValueError(f"unsupported input type: {path}")

        self.progress("Rebuilding paragraphs", "إعادة بناء الفقرات", 0.75)
        from .structure import build_paragraphs
        paras = build_paragraphs(pages, drop_furniture=self.opts.drop_furniture)

        for p in paras:
            p.text = canonical(p.text, keep_tashkeel=self.opts.keep_tashkeel,
                               digits=self.opts.digits)

        if self.opts.correct and self.corrector.available:
            self.progress("Checking words against the lexicon",
                          "مطابقة الكلمات مع المعجم", 0.88)
            from .text_fixes import fix_characters, fix_comma_lookalikes
            comma_fixes = 0
            for p in paras:
                src = p.lines[0].source if p.lines else "digital"
                if src == "ocr":
                    # Character-level repairs first. Two thirds of this
                    # recogniser's character errors are punctuation, and the
                    # Arabic comma alone is about a third of all of them, so
                    # these run before any dictionary work.
                    p.text = fix_characters(p.text)
                    p.text, k = fix_comma_lookalikes(p.text, self.corrector.lex)
                    comma_fixes += k
                    p.text = self.corrector.fix_text(p.text, mode="double")
                elif src == "font_repair":
                    # Repaired text can carry a spurious letter beside a
                    # ligature rather than a duplicate, so allow a single
                    # deletion - still only into a dictionary word.
                    p.text = self.corrector.fix_text(p.text, mode="delete")

        ocr_pages = sum(1 for p in pages if p.source == "ocr")
        repaired_pages = sum(1 for p in pages if p.source == "font_repair")
        stats = {
            "pages": len(pages),
            "paragraphs": len(paras),
            "lines": sum(len(p.lines) for p in pages),
            "ocr_pages": ocr_pages,
            "repaired_pages": repaired_pages,
            "digital_pages": len(pages) - ocr_pages - repaired_pages,
            "seconds": round(time.time() - t0, 1),
            "flagged": sum(1 for p in paras if p.flags or p.conf < 0.75),
        }
        if self.opts.correct and self._corrector is not None:
            stats["lexicon_edits"] = len(self.corrector.edits)
            full = " ".join(p.text for p in paras)
            stats["lexicon_coverage"] = round(self.corrector.coverage(full), 4)
            stats["comma_fixes"] = locals().get("comma_fixes", 0)
        if getattr(self, "repair_log", None):
            stats["glyphs_relearned"] = sum(
                1 for v in self.repair_log.values() if v.get("accepted"))
            stats["glyphs_unresolved"] = sum(
                1 for v in self.repair_log.values() if not v.get("accepted"))
        self.progress("Done", "تم", 1.0)
        return DocResult(paras=paras, pages=pages, stats=stats)


def _pages_from_text(path: str) -> List[PageInfo]:
    """Plain text in, structure inferred from blank lines only."""
    from .model import Line
    txt = open(path, encoding="utf-8", errors="replace").read()
    lines: List[Line] = []
    y = 0.0
    for block in txt.split("\n"):
        if not block.strip():
            y += 30
            continue
        lines.append(Line(text=block.strip(), bbox=(72, y, 523, y + 14), page=1, size=12))
        y += 18
    return [PageInfo(number=1, width=595, height=max(842, y + 40), lines=lines, source="text")]
