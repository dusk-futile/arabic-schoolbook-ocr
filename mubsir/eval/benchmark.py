"""The headline numbers, all measured in one run.

Answers three questions a user actually asks: how accurate is it, how fast is
it, and how does it compare with what I would otherwise do.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pymupdf

from eval.metrics import (boundary_scores, cer, hallucination_rate,
                          reading_order_accuracy, wer)
from mubsir.arabic import canonical
from mubsir.lexicon import Corrector, Lexicon
from mubsir.lines import merge_fragments
from mubsir.model import PageInfo
from mubsir.pdf_text import extract_page_lines
from mubsir.structure import build_paragraphs, order_page_lines, page_geometry

SYNTH = "eval/synth"
STYLES = ["indent_tight", "indent_spaced", "spaced", "ragged", "two_col"]


def _in(line, rect, tol=8.0):
    x0, y0, x1, y1 = rect
    return y0 - tol <= line.cy <= y1 + tol and x0 - tol <= line.cx <= x1 + tol


def measure(pages, gold, n):
    gold_of = {}
    for gp in gold["pages"][:n]:
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
    truth = canonical(" ".join(pa["text"] for gp in gold["pages"][:n]
                               for pa in gp["paras"]))
    hyp = canonical(" ".join(p.text for p in paras))
    sc = boundary_scores([a for a, _ in seq], [b for _, b in seq]) if len(seq) > 4 else None
    return {
        "cer": cer(truth, hyp), "wer": wer(truth, hyp),
        "halluc": hallucination_rate(truth, hyp),
        "f1": sc["f1"] if sc else float("nan"),
        "order": reading_order_accuracy([a for a, _ in seq]),
    }


def page_img(doc, i, dpi=300):
    pix = doc[i].get_pixmap(dpi=dpi)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(a, cv2.COLOR_RGB2BGR if pix.n == 3 else cv2.COLOR_RGBA2BGR)


def run_engine(engine_name, n=4):
    from mubsir.ocr import get_engine
    eng = get_engine(engine_name)
    rows, secs = {}, []
    for style in STYLES:
        pdf = os.path.join(SYNTH, f"{style}.pdf")
        gold = json.load(open(pdf.replace(".pdf", ".gold.json"), encoding="utf-8"))
        doc = pymupdf.open(pdf)
        m = min(n, doc.page_count)
        t0 = time.time()
        pages = [PageInfo(number=i + 1, width=595, height=842, source="ocr",
                          lines=merge_fragments(eng.page_lines(page_img(doc, i), i + 1, 300 / 72.0)))
                 for i in range(m)]
        secs.append((time.time() - t0) / m)
        rows[style] = measure(pages, gold, m)
    return rows, statistics.fmean(secs)


def run_digital(n=8):
    rows = {}
    for style in STYLES:
        pdf = os.path.join(SYNTH, f"{style}.pdf")
        gold = json.load(open(pdf.replace(".pdf", ".gold.json"), encoding="utf-8"))
        doc = pymupdf.open(pdf)
        m = min(n, doc.page_count)
        pages = [PageInfo(number=i + 1, width=doc[i].rect.width, height=doc[i].rect.height,
                          lines=extract_page_lines(doc[i], i + 1)) for i in range(m)]
        rows[style] = measure(pages, gold, m)
    return rows


def mean_of(rows, key, exclude_two_col=True):
    vals = [v[key] for k, v in rows.items() if not (exclude_two_col and k == "two_col")]
    return statistics.fmean(vals)


def main():
    out = {}
    print("=" * 78)
    print("STRUCTURE  (born-digital text layer, exact geometry, 8 pages x 5 styles)")
    print("=" * 78)
    dig = run_digital()
    out["digital"] = dig
    print(f"{'style':<16}{'paragraph F1':>14}{'reading order':>16}")
    for k, v in dig.items():
        print(f"{k:<16}{v['f1']:>14.4f}{v['order']:>16.4f}")
    print(f"{'MEAN (all)':<16}{statistics.fmean(v['f1'] for v in dig.values()):>14.4f}"
          f"{statistics.fmean(v['order'] for v in dig.values()):>16.4f}")

    print()
    print("=" * 78)
    print("SCANNED PATH  (text layer discarded, 4 pages x 5 styles)")
    print("=" * 78)
    print(f"{'engine':<22}{'CER':>8}{'WER':>8}{'halluc':>9}{'paraF1':>9}{'order':>8}{'s/page':>9}")
    for name in ["hybrid", "tesseract", "ppocr-arabic"]:
        try:
            rows, sec = run_engine(name)
        except Exception as e:
            print(f"{name:<22}  unavailable: {type(e).__name__}")
            continue
        out[name] = {"rows": rows, "sec_per_page": sec}
        print(f"{name + ' (1-col)':<22}{mean_of(rows,'cer'):>8.4f}{mean_of(rows,'wer'):>8.4f}"
              f"{mean_of(rows,'halluc'):>9.4f}{mean_of(rows,'f1'):>9.4f}"
              f"{mean_of(rows,'order'):>8.4f}{sec:>9.2f}")
        tc = rows["two_col"]
        print(f"{'  ^ two-column':<22}{tc['cer']:>8.4f}{tc['wer']:>8.4f}"
              f"{tc['halluc']:>9.4f}{tc['f1']:>9.4f}{tc['order']:>8.4f}")

    print()
    print("=" * 78)
    print("REAL BOOK  (209 pages, Word 2010, broken font encoding)")
    print("=" * 78)
    real = "samples/sample_book.pdf"
    if os.path.exists(real):
        from mubsir.font_repair import FontDecoder, calibrate, choose_fonts, decode_page
        lex = Lexicon(); co = Corrector(lex)
        doc = pymupdf.open(real)
        n = doc.page_count
        probe = list(range(0, n, max(1, n // 12)))[:12]
        cal = list(range(0, n, max(1, n // 25)))[:25]
        dec = FontDecoder(doc)
        t0 = time.time()
        choose_fonts(doc, dec, lex, cal)
        res, _ = calibrate(doc, dec, lex, pages=cal)
        dec.apply_overrides(res)
        cal_s = time.time() - t0
        raw, rep, fix = [], [], []
        t0 = time.time()
        for i in probe:
            raw.append(co.coverage(" ".join(l.text for l in extract_page_lines(doc[i], i + 1))))
            r = " ".join(l.text for l in merge_fragments(decode_page(doc, doc[i], i + 1, dec)))
            rep.append(co.coverage(r))
            fix.append(co.coverage(co.fix_text(r, mode="delete")))
        per_page = (time.time() - t0) / len(probe)
        out["real"] = {"raw": statistics.fmean(raw), "repaired": statistics.fmean(rep),
                       "fixed": statistics.fmean(fix), "sec_per_page": per_page,
                       "calibration_s": cal_s, "pages": n}
        print(f"  words that are real Arabic words:")
        print(f"    just opening the PDF and copying   {statistics.fmean(raw):>8.1%}")
        print(f"    after font repair                  {statistics.fmean(rep):>8.1%}")
        print(f"    after lexicon correction           {statistics.fmean(fix):>8.1%}")
        print(f"    clean Arabic prose, same lexicon      87.0%   (reference ceiling)")
        print(f"  speed: {per_page:.2f} s/page + {cal_s:.1f} s one-off calibration")
        print(f"         {n} pages in about {(per_page*n + cal_s):.0f} s")
    json.dump(out, open("eval/results_benchmark.json", "w"), indent=1, default=float)
    print("\nwrote eval/results_benchmark.json")


if __name__ == "__main__":
    main()
