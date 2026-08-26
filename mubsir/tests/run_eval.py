"""One command that regenerates every accuracy claim in the repo."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

import pymupdf

from mubsir.tests.metrics import boundary_scores, cer, wer
from mubsir.pdf_text import extract_page_lines, layer_quality
from mubsir.structure import build_paragraphs, find_furniture, order_page_lines, page_geometry
from mubsir.model import PageInfo


def _in_rect(line, rect, tol=3.0):
    x0, y0, x1, y1 = rect
    return (line.cy >= y0 - tol and line.cy <= y1 + tol
            and line.cx >= x0 - tol and line.cx <= x1 + tol)


def eval_doc(pdf_path, gold_path):
    gold = json.load(open(gold_path, encoding="utf-8"))
    doc = pymupdf.open(pdf_path)
    pages = []
    for i in range(doc.page_count):
        pg = doc[i]
        pages.append(PageInfo(number=i + 1, width=pg.rect.width, height=pg.rect.height,
                              lines=extract_page_lines(pg, i + 1)))
    quality = layer_quality([l for p in pages for l in p.lines])

    # map every extracted line to its gold paragraph via geometry
    gold_of = {}
    for gp in gold["pages"]:
        for para in gp["paras"]:
            for line in pages[gp["page"] - 1].lines:
                if _in_rect(line, para["rect"]):
                    gold_of[id(line)] = para["id"]

    paras = build_paragraphs(pages, drop_furniture=True)
    pred_of = {}
    for idx, p in enumerate(paras):
        for line in p.lines:
            pred_of[id(line)] = idx

    # evaluate in the pipeline's own reading order
    seq = []
    for p in pages:
        keep = [l for l in p.lines if l.text.strip()]
        g = page_geometry(keep, p.width, p.height)
        ordered = order_page_lines(keep, g) if g else keep
        for line in ordered:
            if id(line) in gold_of and id(line) in pred_of:
                seq.append((gold_of[id(line)], pred_of[id(line)]))
    if not seq:
        return {"doc": os.path.basename(pdf_path), "error": "no aligned lines"}

    g_ids = [a for a, _ in seq]
    p_ids = [b for _, b in seq]
    sc = boundary_scores(g_ids, p_ids)

    furniture = find_furniture(pages)
    total_lines = sum(len(p.lines) for p in pages)
    return {
        "doc": os.path.basename(pdf_path),
        "style": gold.get("style"),
        "pages": len(pages),
        "lines": total_lines,
        "aligned": len(seq),
        "gold_paras": sum(len(p["paras"]) for p in gold["pages"]),
        "pred_paras": len(paras),
        "furniture_dropped": len(furniture),
        "boundary_f1": round(sc["f1"], 4),
        "precision": round(sc["precision"], 4),
        "recall": round(sc["recall"], 4),
        "false_breaks": sc["fp"],
        "missed_breaks": sc["fn"],
        "n_gaps": sc["n_gaps"],
        "layer_corruption": quality["corruption"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synth", default="mubsir/tests/synth")
    args = ap.parse_args()
    rows = []
    for pdf in sorted(glob.glob(os.path.join(args.synth, "*.pdf"))):
        gold = pdf.replace(".pdf", ".gold.json")
        if not os.path.exists(gold):
            continue
        rows.append(eval_doc(pdf, gold))

    hdr = ["style", "pages", "lines", "gold_paras", "pred_paras",
           "boundary_f1", "false_breaks", "missed_breaks", "n_gaps"]
    print(f"{'style':<15}{'pgs':>4}{'lines':>7}{'gold':>6}{'pred':>6}"
          f"{'F1':>9}{'FP':>5}{'FN':>5}{'gaps':>6}")
    print("-" * 63)
    tot_tp = tot_fp = tot_fn = 0
    for r in rows:
        if "error" in r:
            print(r["doc"], r["error"]); continue
        print(f"{r['style']:<15}{r['pages']:>4}{r['lines']:>7}{r['gold_paras']:>6}"
              f"{r['pred_paras']:>6}{r['boundary_f1']:>9.4f}{r['false_breaks']:>5}"
              f"{r['missed_breaks']:>5}{r['n_gaps']:>6}")
    json.dump(rows, open("mubsir/tests/results_structure.json", "w"), indent=1)
    print("\nwrote tests/results_structure.json")


if __name__ == "__main__":
    main()
