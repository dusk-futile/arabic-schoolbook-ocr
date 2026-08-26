"""Command line entry point.

Prints progress in Arabic and English, because the operators are Arabic-first.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .docx_out import build_docx, build_plain_text
from .pdf_out import build_review_pdf
from .pipeline import Options, Pipeline
from .report import write_report

BANNER = "مُبصِر  mubsir - Arabic document to clean text"


def _progress(en: str, ar: str, frac: float) -> None:
    bar = int(frac * 28)
    sys.stdout.write(f"\r[{'#' * bar}{'.' * (28 - bar)}] {frac*100:5.1f}%  {en} / {ar}      ")
    sys.stdout.flush()
    if frac >= 1.0:
        sys.stdout.write("\n")


def process_one(path: str, outdir: str, opts: Options, quiet: bool = False) -> dict:
    name = os.path.splitext(os.path.basename(path))[0]
    pipe = Pipeline(opts, progress=(lambda *_: None) if quiet else _progress)
    res = pipe.run(path)
    os.makedirs(outdir, exist_ok=True)
    docx_path = os.path.join(outdir, f"{name}.docx")
    txt_path = os.path.join(outdir, f"{name}.txt")
    pdf_path = os.path.join(outdir, f"{name}.review.pdf")
    rep_path = os.path.join(outdir, f"{name}.review.html")
    build_docx(res.paras, docx_path)
    build_plain_text(res.paras, txt_path)
    try:
        build_review_pdf(res.paras, pdf_path)
    except Exception as e:                      # never fail the run over the PDF
        pdf_path = None
        res.warnings.append(f"review PDF failed: {type(e).__name__}: {e}")
    write_report(res, rep_path, source_name=os.path.basename(path))
    res.stats["outputs"] = {"docx": docx_path, "txt": txt_path,
                            "pdf": pdf_path, "report": rep_path}
    return res.stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mubsir", description=BANNER)
    ap.add_argument("inputs", nargs="*", help="PDF, image, folder of images, or .txt")
    ap.add_argument("-o", "--output", default="output")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--no-ocr", action="store_true", help="never OCR; digital text layers only")
    ap.add_argument("--force-ocr", action="store_true", help="ignore the text layer entirely")
    ap.add_argument("--no-correct", action="store_true", help="disable the lexicon corrector")
    ap.add_argument("--keep-furniture", action="store_true",
                    help="keep running heads and page numbers")
    ap.add_argument("--strip-tashkeel", action="store_true")
    ap.add_argument("--digits", choices=["keep", "western", "arabic_indic"], default="keep")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--engine", default="auto",
                    help="auto (best available), hybrid, tesseract, ppocr-arabic")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json", action="store_true", help="emit stats as JSON")
    args = ap.parse_args(argv)

    inputs = args.inputs
    if not inputs:
        if os.path.isdir("input"):
            inputs = [os.path.join("input", f) for f in sorted(os.listdir("input"))
                      if not f.startswith(".")]
        if not inputs:
            ap.print_help()
            print("\nNo inputs. Put files in ./input/ or pass paths.")
            return 2

    opts = Options(
        engine=args.engine,
        ocr=not args.no_ocr,
        force_ocr=args.force_ocr,
        dpi=args.dpi,
        keep_tashkeel=not args.strip_tashkeel,
        digits=args.digits,
        correct=not args.no_correct,
        drop_furniture=not args.keep_furniture,
        max_pages=args.max_pages,
    )
    if not args.quiet:
        print(BANNER)
    all_stats = []
    for path in inputs:
        if not os.path.exists(path):
            print(f"missing: {path}", file=sys.stderr)
            continue
        if not args.quiet:
            print(f"\n>> {os.path.basename(path)}")
        try:
            st = process_one(path, args.output, opts, quiet=args.quiet)
        except Exception as e:
            print(f"\nFAILED {path}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        all_stats.append({"input": path, **st})
        if not args.quiet:
            o = st["outputs"]
            print(f"   pages={st['pages']} paragraphs={st['paragraphs']} "
                  f"flagged={st['flagged']} time={st['seconds']}s")
            print(f"   Word     : {o['docx']}")
            print(f"   Review PDF: {o['pdf']}")
            print(f"   Text     : {o['txt']}")
            print(f"   Report   : {o['report']}")
    if args.json:
        print(json.dumps(all_stats, ensure_ascii=False, indent=1))
    return 0 if all_stats else 1


if __name__ == "__main__":
    raise SystemExit(main())
