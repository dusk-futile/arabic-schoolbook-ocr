"""Run both paths over the demo pages and print measured accuracy.

Nothing here is hard-coded: every number is computed against the ground truth
in demo/pages/*.gold.json.
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2
import numpy as np
import pymupdf

from eval.metrics import boundary_scores, cer, reading_order_accuracy, wer
from mubsir.arabic import canonical
from mubsir.lines import merge_fragments
from mubsir.model import PageInfo
from mubsir.pdf_text import extract_page_lines
from mubsir.structure import build_paragraphs, order_page_lines, page_geometry

PAGES = os.path.join(ROOT, "demo", "pages")


def _in(line, rect, tol=8.0):
    x0, y0, x1, y1 = rect
    return y0 - tol <= line.cy <= y1 + tol and x0 - tol <= line.cx <= x1 + tol


def score(pages, gold, label, secs, text_meaningful=True):
    gold_of = {}
    for gp in gold["pages"][: len(pages)]:
        for para in gp["paras"]:
            for line in pages[gp["page"] - 1].lines:
                if _in(line, para["rect"]):
                    gold_of[id(line)] = para["id"]
    paras = build_paragraphs(pages, drop_furniture=True)
    pred_of = {}
    for i, p in enumerate(paras):
        for line in p.lines:
            pred_of[id(line)] = i
    seq = []
    for p in pages:
        keep = [l for l in p.lines if l.text.strip()]
        g = page_geometry(keep, p.width, p.height)
        for line in (order_page_lines(keep, g) if g else keep):
            if id(line) in gold_of and id(line) in pred_of:
                seq.append((gold_of[id(line)], pred_of[id(line)]))
    truth = canonical(" ".join(pa["text"] for gp in gold["pages"][: len(pages)]
                               for pa in gp["paras"]))
    hyp = canonical(" ".join(p.text for p in paras))
    sc = boundary_scores([a for a, _ in seq], [b for _, b in seq]) if len(seq) > 4 else None
    txt = (f"CER={cer(truth, hyp):.3f}  WER={wer(truth, hyp):.3f}"
           if text_meaningful else "CER=  n/a   WER=  n/a ")
    print(f"  {label:<32} {txt}  "
          f"paraF1={(sc['f1'] if sc else float('nan')):.3f}  "
          f"order={reading_order_accuracy([a for a, _ in seq]):.3f}  "
          f"{secs:.1f}s")


def run(name: str):
    pdf = os.path.join(PAGES, f"{name}.pdf")
    gold = json.load(open(os.path.join(PAGES, f"{name}.gold.json"), encoding="utf-8"))
    doc = pymupdf.open(pdf)
    print(f"\n{name}  ({doc.page_count} pages)")

    t = time.time()
    dig = [PageInfo(number=i + 1, width=doc[i].rect.width, height=doc[i].rect.height,
                    lines=extract_page_lines(doc[i], i + 1)) for i in range(doc.page_count)]
    # These demo PDFs deliberately carry the broken kind of Arabic text layer
    # (shaped presentation glyphs with a damaged character map), because that
    # is what real Arabic PDFs do. Its geometry is exact, so structure scores
    # perfectly; its characters are mojibake, so CER on it is meaningless and
    # is not reported. That contrast is the point - see RESEARCH.md section 1.
    score(dig, gold, "digital layer (structure only)", time.time() - t,
          text_meaningful=False)

    from mubsir.ocr import best_available
    eng = best_available()
    t = time.time()
    ocr = []
    for i in range(doc.page_count):
        pix = doc[i].get_pixmap(dpi=300)
        a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
        img = cv2.cvtColor(a, cv2.COLOR_RGB2BGR if pix.n == 3 else cv2.COLOR_RGBA2BGR)
        ocr.append(PageInfo(number=i + 1, width=595, height=842, source="ocr",
                            lines=merge_fragments(eng.page_lines(img, i + 1, 300 / 72.0))))
    score(ocr, gold, f"scanned ({eng.name})", time.time() - t)


if __name__ == "__main__":
    print("mubsir demo - every number measured against demo/pages/*.gold.json")
    print("The digital row shows structure only: these pages carry the broken")
    print("kind of Arabic text layer on purpose, so its characters are mojibake")
    print("while its geometry is exact. The scanned row is the full OCR path.")
    for n in ["indent_tight", "two_col"]:
        run(n)
    print("\nTo convert your own file:")
    print("  python -m mubsir yourfile.pdf -o output")
