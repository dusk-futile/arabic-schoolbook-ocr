"""A clean PDF laid out for fast human proofreading.

This is the artifact a volunteer reads *before* the book is embossed. It is
deliberately not a facsimile of the original: Braille is linear, so the page
reproduces semantic structure and nothing else. What it optimises for is the
speed of the review pass -

  * large type and wide leading, because the reader may be partially sighted;
  * one paragraph per block with visible separation, so a wrong paragraph
    break is obvious at a glance rather than buried mid-column;
  * a paragraph number in the margin, so a reviewer can say "paragraph 214"
    and the operator can find it instantly;
  * the source page number, so anything doubtful can be checked against the
    original scan;
  * uncertain paragraphs shaded, so review is skimming rather than reading.

The embosser itself is fed the .docx or .brf; this PDF exists for the human.
"""
from __future__ import annotations

import html
from typing import Iterable, List, Optional

import pymupdf

from .model import (BODY, CAPTION, FOOTNOTE, HEADING, LIST_ITEM, SUBHEADING,
                    TITLE, Para)

PAGE_W, PAGE_H = 595.0, 842.0
MARGIN = 52.0
GUTTER = 46.0          # margin strip holding paragraph numbers

CSS = """
* { font-family: sans-serif; direction: rtl; }
body { font-size: 14.5px; line-height: 2.0; }
div.p { text-align: justify; margin: 0 0 13px 0; }
div.flag { background-color: #fff2ab; }
h1 { font-size: 23px; text-align: center; margin: 18px 0 12px 0; line-height: 1.5; }
h2 { font-size: 18.5px; margin: 16px 0 8px 0; line-height: 1.5; }
h3 { font-size: 16px; margin: 13px 0 6px 0; line-height: 1.5; }
div.li { text-align: right; margin: 0 22px 8px 0; }
div.fn { font-size: 12px; color: #444; margin: 0 0 7px 0; }
span.n { font-size: 10px; color: #8a8a8a; }
span.pg { font-size: 10px; color: #b03030; }
"""

TAG = {
    TITLE: ("h1", ""), HEADING: ("h2", ""), SUBHEADING: ("h3", ""),
    LIST_ITEM: ("div", "li"), FOOTNOTE: ("div", "fn"),
    CAPTION: ("div", "fn"), BODY: ("div", "p"),
}


def _block(index: int, para: Para, show_numbers: bool, show_pages: bool) -> str:
    tag, cls = TAG.get(para.kind, ("div", "p"))
    flagged = bool(para.flags) or para.conf < 0.75
    classes = " ".join(c for c in [cls, "flag" if flagged else ""] if c)
    marker = ""
    if show_numbers:
        marker += f"<span class='n'>[{index}]</span> "
    if show_pages and para.page:
        marker += f"<span class='pg'>ص{para.page}</span> "
    body = html.escape(para.text)
    attr = f" class='{classes}'" if classes else ""
    return f"<{tag}{attr} dir='rtl'>{marker}{body}</{tag}>"


def build_review_pdf(paras: Iterable[Para], out_path: str, *,
                     title: Optional[str] = None,
                     show_numbers: bool = True,
                     show_pages: bool = True,
                     font_px: float = 14.5) -> str:
    paras = [p for p in paras if p.text.strip()]
    parts: List[str] = []
    if title:
        parts.append(f"<h1 dir='rtl'>{html.escape(title)}</h1>")
    for i, para in enumerate(paras, 1):
        parts.append(_block(i, para, show_numbers, show_pages))
    css = CSS.replace("font-size: 14.5px", f"font-size: {font_px}px")
    story = pymupdf.Story(html=f"<body dir='rtl'>{''.join(parts)}</body>", user_css=css)

    writer = pymupdf.DocumentWriter(out_path)
    rect = pymupdf.Rect(MARGIN, MARGIN, PAGE_W - MARGIN, PAGE_H - MARGIN)
    more, guard = 1, 0
    while more and guard < 5000:
        guard += 1
        dev = writer.begin_page(pymupdf.Rect(0, 0, PAGE_W, PAGE_H))
        more, _ = story.place(rect)
        story.draw(dev)
        writer.end_page()
    writer.close()

    # Stamp page numbers. Story has no footer concept, so they go on afterwards.
    doc = pymupdf.open(out_path)
    for i, page in enumerate(doc, 1):
        page.insert_text(pymupdf.Point(PAGE_W / 2 - 10, PAGE_H - 26),
                         str(i), fontsize=9, color=(0.45, 0.45, 0.45))
    doc.saveIncr()
    doc.close()
    return out_path
