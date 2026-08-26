"""Generate realistic Arabic book pages with exact ground truth.

Why synthetic pages exist alongside real scans: they give a line-to-paragraph
mapping that is known rather than guessed, so paragraph-boundary F1 can be
measured on hundreds of pages instead of the fifteen a human can transcribe.
They do NOT replace real scans - synthetic degradation is always kinder than
a real scanner - so every reported number says which set it came from.
"""
from __future__ import annotations

import glob
import json
import os
import random
import sys

import pymupdf

PAGE_W, PAGE_H = 595.0, 842.0
MARGIN_X, MARGIN_TOP, MARGIN_BOT = 78.0, 84.0, 76.0

STYLES = {
    # The hardest and most common Arabic book style: justified, first-line
    # indent, no extra space between paragraphs. Vertical gap is useless here,
    # so the engine must rely on line-fill and indent.
    "indent_tight": dict(justify=True, indent=20, para_gap=0.0, columns=1),
    # Spacing instead of indent - the easy case.
    "spaced": dict(justify=True, indent=0, para_gap=7.0, columns=1),
    # Both signals present.
    "indent_spaced": dict(justify=True, indent=18, para_gap=5.0, columns=1),
    # Ragged left edge (unjustified) - line-fill signal becomes unreliable.
    "ragged": dict(justify=False, indent=18, para_gap=2.0, columns=1),
    # Two-column, RTL reading order.
    "two_col": dict(justify=True, indent=14, para_gap=0.0, columns=2),
}

FONT_STACK = "sans-serif"


CORPUS_DIRS = ["eval/corpus", "demo/corpus"]


def load_corpus(path=None):
    """Prefer a locally fetched corpus, else the bundled demo one."""
    dirs = [path] if path else CORPUS_DIRS
    paras = []
    files = []
    for d in dirs:
        files = sorted(glob.glob(os.path.join(d, "*.txt")))
        if files:
            break
    for f in files:
        if os.path.basename(f) == "SOURCES.txt":
            continue
        for p in open(f, encoding="utf-8").read().split("\n\n"):
            p = " ".join(p.split())
            if len(p) > 120:
                paras.append(p)
    return paras


def css_for(style, size=12.5, indent=0, justify=True):
    align = "justify" if justify else "right"
    return (
        f"* {{font-family:{FONT_STACK}; font-size:{size}px; direction:rtl;"
        f" text-align:{align}; line-height:1.72; text-indent:{indent}px;"
        f" margin:0; padding:0;}}"
        f" h1 {{font-size:{size*1.55:.1f}px; text-align:center; text-indent:0;"
        f" font-weight:bold; line-height:1.5;}}"
        f" h2 {{font-size:{size*1.22:.1f}px; text-align:right; text-indent:0;"
        f" font-weight:bold; line-height:1.5;}}"
        f" li {{text-indent:0;}}"
    )


def measure(html, css, rect):
    st = pymupdf.Story(html=html, user_css=css)
    more, filled = st.place(rect)
    return more, pymupdf.Rect(filled)


def make_doc(out_pdf, out_gold, style_name="indent_tight", n_pages=8, seed=7,
             heading_every=6, running_head="سيكولوجية الإبداع والموهوبون"):
    rnd = random.Random(seed)
    st = STYLES[style_name]
    corpus = load_corpus()
    if not corpus:
        raise SystemExit("no corpus - run the fetch step first")
    rnd.shuffle(corpus)

    doc = pymupdf.open()
    gold = {"style": style_name, "pages": []}
    ci = 0
    ncols = st["columns"]
    col_gap = 22.0
    col_w = (PAGE_W - 2 * MARGIN_X - (ncols - 1) * col_gap) / ncols

    para_no = 0
    for pno in range(1, n_pages + 1):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page_gold = {"page": pno, "paras": []}

        # running head + page number = furniture the pipeline must discard
        page.insert_htmlbox(
            pymupdf.Rect(MARGIN_X, 40, PAGE_W - MARGIN_X, 64),
            f"<div dir='rtl'>{running_head}</div>",
            css=css_for(st, size=9.5, indent=0, justify=False),
        )
        page.insert_htmlbox(
            pymupdf.Rect(MARGIN_X, PAGE_H - 58, PAGE_W - MARGIN_X, PAGE_H - 36),
            f"<div style='text-align:center'>{pno}</div>",
            css="*{font-family:sans-serif;font-size:10px;text-align:center;}",
        )

        for col in range(ncols):
            # RTL: column 0 is the rightmost
            x1 = PAGE_W - MARGIN_X - col * (col_w + col_gap)
            x0 = x1 - col_w
            y = MARGIN_TOP
            bottom = PAGE_H - MARGIN_BOT
            guard = 0
            while y < bottom - 30 and guard < 60:
                guard += 1
                para_no += 1
                is_heading = (para_no % heading_every == 0)
                text = corpus[ci % len(corpus)]
                ci += 1
                if is_heading:
                    kind = "heading"
                    body = text.split("،")[0][:58].strip() or text[:40]
                    html = f"<h2 dir='rtl'>{body}</h2>"
                    css = css_for(st, indent=0, justify=False)
                else:
                    kind = "body"
                    body = text
                    html = f"<div dir='rtl'>{body}</div>"
                    css = css_for(st, indent=st["indent"], justify=st["justify"])

                probe = pymupdf.Rect(x0, y, x1, bottom)
                more, filled = measure(html, css, probe)
                if more:
                    # would overflow the column; stop this column cleanly
                    break
                h = filled.height
                if h <= 0 or y + h > bottom:
                    break
                target = pymupdf.Rect(x0, y, x1, y + h + 2)
                page.insert_htmlbox(target, html, css=css)
                page_gold["paras"].append({
                    "id": para_no, "kind": kind, "text": body, "column": col,
                    "rect": [round(v, 2) for v in (x0, y, x1, y + h + 2)],
                })
                y += h + 2 + st["para_gap"]
        gold["pages"].append(page_gold)

    doc.save(out_pdf, garbage=3, deflate=True)
    json.dump(gold, open(out_gold, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    npara = sum(len(p["paras"]) for p in gold["pages"])
    print(f"{out_pdf}: {n_pages} pages, {npara} paragraphs, style={style_name}")
    return gold


if __name__ == "__main__":
    os.makedirs("eval/synth", exist_ok=True)
    for name in STYLES:
        make_doc(f"eval/synth/{name}.pdf", f"eval/synth/{name}.gold.json",
                 style_name=name, n_pages=8, seed=hash(name) % 1000)
