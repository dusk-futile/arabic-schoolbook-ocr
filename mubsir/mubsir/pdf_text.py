"""Born-digital PDF front-end.

A text layer existing is NOT the same as a text layer being usable. Arabic
PDFs very often store shaped presentation-form glyphs with broken ToUnicode
maps, so extraction yields plausible-looking mojibake. ``layer_quality``
measures that, and the router uses it to decide OCR vs direct extraction.
"""
from __future__ import annotations

import statistics
from typing import List

import pymupdf

from .arabic import canonical, char_profile
from .lines import merge_fragments
from .model import Line, PageInfo


def _span_bold(span) -> bool:
    name = (span.get("font") or "").lower()
    if "bold" in name or "black" in name or "heavy" in name:
        return True
    return bool(span.get("flags", 0) & 2 ** 4)


def extract_page_lines(page: pymupdf.Page, page_no: int) -> List[Line]:
    """Pull lines with geometry. Never sort by position - MuPDF already emits
    logical (reading) order, and positional sorting destroys RTL."""
    out: List[Line] = []
    d = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES)
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for ln in block.get("lines", []):
            spans = [s for s in ln.get("spans", []) if s.get("text")]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans)
            if not text.strip():
                continue
            sizes = [s.get("size", 12.0) for s in spans]
            weights = [max(len(s["text"].strip()), 1) for s in spans]
            try:
                size = statistics.median(
                    [sz for sz, w in zip(sizes, weights) for _ in range(w)]
                )
            except statistics.StatisticsError:
                size = sizes[0]
            bold = sum(w for s, w in zip(spans, weights) if _span_bold(s)) > sum(weights) / 2
            fonts = max(spans, key=lambda s: len(s["text"]))
            out.append(
                Line(
                    text=text,
                    bbox=tuple(ln["bbox"]),
                    page=page_no,
                    size=round(size, 2),
                    conf=1.0,
                    source="digital",
                    bold=bold,
                    font=fonts.get("font", ""),
                )
            )
    return merge_fragments(out)


def layer_quality(lines: List[Line]) -> dict:
    """How much should we trust this text layer?

    corruption = share of letters that land outside any script we expect.
    Broken Arabic CMaps produce Latin-Extended and IPA characters where
    Arabic letters belong, so this catches them precisely.
    """
    text = canonical("\n".join(l.text for l in lines))
    p = char_profile(text)
    letters = p["arabic"] + p["foreign"] + p["ascii"]
    corruption = p["foreign"] / letters if letters else 0.0
    arabic_share = p["arabic"] / letters if letters else 0.0
    return {
        "chars": len(text),
        "letters": letters,
        "arabic": p["arabic"],
        "foreign": p["foreign"],
        "corruption": round(corruption, 4),
        "arabic_share": round(arabic_share, 4),
        "n_lines": len(lines),
    }


def read_pdf(path: str, max_pages: int | None = None) -> List[PageInfo]:
    doc = pymupdf.open(path)
    pages: List[PageInfo] = []
    n = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
    for i in range(n):
        page = doc[i]
        lines = extract_page_lines(page, i + 1)
        pages.append(
            PageInfo(
                number=i + 1,
                width=page.rect.width,
                height=page.rect.height,
                lines=lines,
                source="digital",
            )
        )
    doc.close()
    return pages
