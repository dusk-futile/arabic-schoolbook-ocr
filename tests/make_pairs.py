"""Generate aligned (what OCR read, what it should have read) training pairs.

The corrector is trained on this pipeline's own mistakes rather than on a
generic error model, because the mistakes are systematic and specific to this
recogniser: it confuses particular Arabic letters, drops particular marks, and
splits particular letter shapes. A confusion model learned from another
system's errors would be fitting the wrong distribution.

Pairs are produced by rendering pages whose text is already known, running the
real OCR path over them, and aligning the two word sequences. Unlimited data,
exact labels, no annotation.
"""
from __future__ import annotations

import difflib
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pymupdf

from mubsir.arabic import canonical
from mubsir.lines import merge_fragments
from mubsir.model import PageInfo
from mubsir.structure import order_page_lines, page_geometry

OUT = "tests/pairs.jsonl"


def page_image(doc, i, dpi=300):
    pix = doc[i].get_pixmap(dpi=dpi)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(a, cv2.COLOR_RGB2BGR if pix.n == 3 else cv2.COLOR_RGBA2BGR)


def ocr_page_text(engine, doc, i, dpi=300):
    img = page_image(doc, i, dpi)
    lines = merge_fragments(engine.page_lines(img, i + 1, dpi / 72.0))
    keep = [l for l in lines if l.text.strip()]
    if not keep:
        return ""
    g = page_geometry(keep, 595.0, 842.0)
    ordered = order_page_lines(keep, g) if g else keep
    return canonical(" ".join(l.text for l in ordered))


def align_words(truth: str, hyp: str):
    """Yield (ocr_words, true_words, left_ctx, right_ctx) for every difference.

    Runs of unequal words are kept together rather than split, so a merge
    ("هذا" read as part of its neighbour) or a split is represented honestly
    instead of being forced into a one-to-one substitution.
    """
    t, h = truth.split(), hyp.split()
    sm = difflib.SequenceMatcher(None, t, h, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        yield (h[j1:j2], t[i1:i2],
               " ".join(t[max(0, i1 - 2):i1]), " ".join(t[i2:i2 + 2]))


def main() -> int:
    from mubsir.ocr import best_available
    engine = best_available()
    pdfs = sorted(glob.glob("tests/train/*.pdf"))
    if not pdfs:
        print("no training PDFs; run eval/make_synthetic.py first")
        return 1

    n_pairs = n_pages = n_correct = n_words = 0
    t0 = time.time()
    with open(OUT, "w", encoding="utf-8") as out:
        for pdf in pdfs:
            gold = json.load(open(pdf.replace(".pdf", ".gold.json"), encoding="utf-8"))
            doc = pymupdf.open(pdf)
            for gp in gold["pages"]:
                i = gp["page"] - 1
                if i >= doc.page_count:
                    continue
                truth = canonical(" ".join(p["text"] for p in gp["paras"]))
                if len(truth.split()) < 10:
                    continue
                hyp = ocr_page_text(engine, doc, i)
                if not hyp:
                    continue
                n_pages += 1
                n_words += len(truth.split())
                sm = difflib.SequenceMatcher(None, truth.split(), hyp.split(),
                                             autojunk=False)
                n_correct += sum(b.size for b in sm.get_matching_blocks())
                for ocr_w, true_w, lc, rc in align_words(truth, hyp):
                    out.write(json.dumps({
                        "ocr": ocr_w, "truth": true_w,
                        "left": lc, "right": rc,
                        "doc": os.path.basename(pdf), "page": gp["page"],
                    }, ensure_ascii=False) + "\n")
                    n_pairs += 1
                if n_pages % 10 == 0:
                    el = time.time() - t0
                    print(f"  {n_pages} pages, {n_pairs} pairs, "
                          f"{el:.0f}s ({el/max(n_pages,1):.1f}s/page)", flush=True)
            doc.close()
    acc = n_correct / max(n_words, 1)
    print(f"\n{n_pages} pages, {n_words} words, word accuracy {acc:.1%}")
    print(f"{n_pairs} error sites -> {OUT} ({os.path.getsize(OUT)//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
