"""End-to-end evaluation of the scanned path.

Renders each synthetic page to an image, throws away the text layer entirely,
and runs the real OCR pipeline over it. Because the gold set records the exact
rectangle of every paragraph, both text accuracy and paragraph-boundary
accuracy are measured against known truth rather than a second guess.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pymupdf

from eval.metrics import (boundary_scores, cer, hallucination_rate,
                          reading_order_accuracy, wer)
from mubsir.arabic import canonical
from mubsir.lines import merge_fragments
from mubsir.model import PageInfo
from mubsir.ocr import get_engine
from mubsir.structure import build_paragraphs, order_page_lines, page_geometry


def page_image(doc, i, dpi):
    pix = doc[i].get_pixmap(dpi=dpi)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        return cv2.cvtColor(a, cv2.COLOR_RGBA2BGR)
    if pix.n == 3:
        return cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)


def in_rect(line, rect, tol=8.0):
    x0, y0, x1, y1 = rect
    return (y0 - tol <= line.cy <= y1 + tol) and (x0 - tol <= line.cx <= x1 + tol)


def eval_ocr(pdf, gold_path, dpi=300, max_pages=4, engine="ppocr-arabic"):
    gold = json.load(open(gold_path, encoding="utf-8"))
    doc = pymupdf.open(pdf)
    eng = get_engine(engine)
    n = min(max_pages, doc.page_count)
    pages, t0 = [], time.time()
    for i in range(n):
        img = page_image(doc, i, dpi)
        scale = dpi / 72.0
        lines = merge_fragments(eng.page_lines(img, i + 1, scale))
        pages.append(PageInfo(number=i + 1, width=img.shape[1] / scale,
                              height=img.shape[0] / scale, lines=lines, source="ocr"))
    ocr_secs = time.time() - t0

    gold_of = {}
    for gp in gold["pages"][:n]:
        for para in gp["paras"]:
            for line in pages[gp["page"] - 1].lines:
                if in_rect(line, para["rect"]):
                    gold_of[id(line)] = para["id"]

    paras = build_paragraphs(pages, drop_furniture=True)
    pred_of = {}
    for idx, p in enumerate(paras):
        for line in p.lines:
            pred_of[id(line)] = idx

    seq = []
    for p in pages:
        keep = [l for l in p.lines if l.text.strip()]
        g = page_geometry(keep, p.width, p.height)
        for line in (order_page_lines(keep, g) if g else keep):
            if id(line) in gold_of and id(line) in pred_of:
                seq.append((gold_of[id(line)], pred_of[id(line)]))
    sc = boundary_scores([a for a, _ in seq], [b for _, b in seq]) if len(seq) > 4 else None
    order_acc = reading_order_accuracy([a for a, _ in seq])

    truth = canonical(" ".join(pa["text"] for gp in gold["pages"][:n] for pa in gp["paras"]))
    hyp = canonical(" ".join(p.text for p in paras))
    return {
        "doc": os.path.basename(pdf), "style": gold.get("style"), "pages": n,
        "sec_per_page": round(ocr_secs / max(n, 1), 2),
        "cer": round(cer(truth, hyp), 4), "wer": round(wer(truth, hyp), 4),
        "halluc": round(hallucination_rate(truth, hyp), 4),
        "boundary_f1": round(sc["f1"], 4) if sc else None,
        "reading_order": round(order_acc, 4),
        "fp": sc["fp"] if sc else None, "fn": sc["fn"] if sc else None,
        "aligned_lines": len(seq),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--pages", type=int, default=4)
    ap.add_argument("--only", default=None)
    ap.add_argument("--engine", default="ppocr-arabic")
    args = ap.parse_args()
    rows = []
    for pdf in sorted(glob.glob("eval/synth/*.pdf")):
        if args.only and args.only not in pdf:
            continue
        rows.append(eval_ocr(pdf, pdf.replace(".pdf", ".gold.json"),
                             dpi=args.dpi, max_pages=args.pages, engine=args.engine))
    print(f"engine: {args.engine}")
    print(f"{'style':<15}{'pgs':>4}{'s/pg':>7}{'CER':>8}{'WER':>8}{'halluc':>8}{'paraF1':>9}{'order':>8}{'FP':>4}{'FN':>4}")
    print("-" * 75)
    for r in rows:
        f1 = f"{r['boundary_f1']:.4f}" if r["boundary_f1"] is not None else "  n/a "
        print(f"{r['style']:<15}{r['pages']:>4}{r['sec_per_page']:>7.2f}{r['cer']:>8.3f}"
              f"{r['wer']:>8.3f}{r['halluc']:>8.3f}{f1:>9}{r['reading_order']:>8.3f}"
              f"{r['fp'] or 0:>4}{r['fn'] or 0:>4}")
    out = f"eval/results_ocr_{args.engine}.json"
    json.dump(rows, open(out, "w"), indent=1)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
