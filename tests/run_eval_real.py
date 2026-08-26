"""Measure text-layer repair on a real document.

There is no hand-transcribed ground truth for a 209-page book, so quality is
measured by dictionary validity: the share of Arabic words that are real
Arabic words. It is a proxy, not a CER, and it is reported as such - but it
separates "this text layer is nonsense" from "this text layer is a book"
unambiguously, which is the question that matters here.

Reference points: clean Arabic prose scores about 0.87 on this lexicon, and a
broken text layer scores about 0.25.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf

from mubsir.font_repair import FontDecoder, calibrate, choose_fonts, decode_page
from mubsir.lexicon import Corrector, Lexicon
from mubsir.lines import merge_fragments
from mubsir.pdf_text import extract_page_lines, layer_quality

REFERENCE = ("الإبداع قدرة عقلية عليا يمتلكها الإنسان وتتجلى في إنتاج أفكار جديدة "
             "وأصيلة ومفيدة في الوقت نفسه وقد اهتم علماء النفس بدراسة هذه الظاهرة")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?", default="samples/sample_book.pdf")
    ap.add_argument("--sample", type=int, default=12)
    args = ap.parse_args()
    if not os.path.exists(args.pdf):
        print(f"missing {args.pdf} - put the source PDF there first")
        return 1

    doc = pymupdf.open(args.pdf)
    lex = Lexicon()
    co = Corrector(lex)
    n = doc.page_count
    step = max(1, n // args.sample)
    probe = list(range(0, n, step))[: args.sample]

    dec = FontDecoder(doc)
    t0 = time.time()
    cal_pages = list(range(0, n, max(1, n // 25)))[:25]
    font_report = choose_fonts(doc, dec, lex, cal_pages)
    resolved, log = calibrate(doc, dec, lex, pages=cal_pages)
    dec.apply_overrides(resolved)
    cal_secs = time.time() - t0

    raw_cov, rep_cov, fix_cov, corruption = [], [], [], []
    for i in probe:
        raw_lines = extract_page_lines(doc[i], i + 1)
        raw = " ".join(l.text for l in raw_lines)
        corruption.append(layer_quality(raw_lines)["corruption"])
        rep = " ".join(l.text for l in merge_fragments(decode_page(doc, doc[i], i + 1, dec)))
        raw_cov.append(co.coverage(raw))
        rep_cov.append(co.coverage(rep))
        fix_cov.append(co.coverage(co.fix_text(rep, mode="delete")))

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    out = {
        "pdf": os.path.basename(args.pdf),
        "pages": n,
        "sampled_pages": len(probe),
        "calibration_seconds": round(cal_secs, 1),
        "glyphs_relearned": sum(1 for v in log.values() if v.get("accepted")),
        "glyphs_refused": sum(1 for v in log.values() if not v.get("accepted")),
        "char_corruption": round(mean(corruption), 4),
        "word_validity_raw_layer": round(mean(raw_cov), 4),
        "word_validity_font_repaired": round(mean(rep_cov), 4),
        "word_validity_after_lexicon_fix": round(mean(fix_cov), 4),
        "reference_clean_arabic": round(co.coverage(REFERENCE), 4),
        "fonts": font_report,
    }
    print(json.dumps({k: v for k, v in out.items() if k != "fonts"},
                     ensure_ascii=False, indent=1))
    print("\nper-font ToUnicode trust:")
    for f, r in sorted(font_report.items(), key=lambda kv: -kv[1]["words"]):
        print(f"  {f[:34]:<35} {r['script']:<7} validity={r['tounicode_validity']:.3f} "
              f"{'TRUSTED' if r['trusted'] else 'REPAIRED'}  ({r['words']} words)")
    json.dump(out, open("tests/results_real.json", "w"), ensure_ascii=False, indent=1)
    print("\nwrote tests/results_real.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
