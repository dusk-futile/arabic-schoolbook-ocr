"""Train the paragraph-boundary classifier, and prove it beats the hand-tuned rules.

The paragraph break is the decision that ruins an emboss when it is wrong, and
it is the one decision for which exact labels exist: the synthetic generator
records the rectangle of every paragraph, so the true answer at every boundary
is known.

The model is deliberately the smallest thing that can work - logistic
regression over eleven geometric features, about ninety bytes of weights. That
matters for three reasons: it runs in microseconds on the target hardware, its
weights are readable so a wrong decision can be explained, and it cannot invent
text because it never sees text, only geometry.

Evaluation is leave-one-style-out: the model is tested on a layout style it
never trained on. That is the honest question, because the charity's next book
will not be one of these five.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pymupdf

from mubsir.model import PageInfo
from mubsir.pdf_text import extract_page_lines
from mubsir.structure import (BREAK_THRESHOLD, FEATURE_NAMES, break_features,
                              decide_break, find_furniture, order_page_lines,
                              page_geometry)

TRAIN_DIR = "mubsir/tests/train"
OUT = os.path.join("mubsir", "models", "boundary_lr.json")


def _in(line, rect, tol=6.0):
    x0, y0, x1, y1 = rect
    return y0 - tol <= line.cy <= y1 + tol and x0 - tol <= line.cx <= x1 + tol


def collect(pdf: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Features, true labels, and what the hand-tuned rules said."""
    gold = json.load(open(pdf.replace(".pdf", ".gold.json"), encoding="utf-8"))
    doc = pymupdf.open(pdf)
    pages = [PageInfo(number=i + 1, width=doc[i].rect.width, height=doc[i].rect.height,
                      lines=extract_page_lines(doc[i], i + 1))
             for i in range(doc.page_count)]
    gold_of = {}
    for gp in gold["pages"]:
        for para in gp["paras"]:
            for line in pages[gp["page"] - 1].lines:
                if _in(line, para["rect"]):
                    gold_of[id(line)] = para["id"]

    furniture = find_furniture(pages)
    X, y, rule = [], [], []
    for p in pages:
        keep = [l for l in p.lines if l.text.strip() and id(l) not in furniture]
        if len(keep) < 3:
            continue
        g = page_geometry(keep, p.width, p.height)
        if g is None:
            continue
        ordered = order_page_lines(keep, g)
        for a, b in zip(ordered, ordered[1:]):
            if id(a) not in gold_of or id(b) not in gold_of:
                continue
            if a.column != b.column:
                continue          # column changes are never in doubt
            gcol = page_geometry([l for l in ordered if l.column == a.column],
                                 p.width, p.height) or g
            X.append(break_features(a, b, gcol))
            y.append(1.0 if gold_of[id(a)] != gold_of[id(b)] else 0.0)
            rule.append(1.0 if decide_break(a, b, gcol).is_break else 0.0)
    doc.close()
    return np.array(X, float), np.array(y, float), np.array(rule, float)


def fit(X: np.ndarray, y: np.ndarray, epochs: int = 4000, lr: float = 0.5,
        l2: float = 1e-3) -> np.ndarray:
    """Plain gradient-descent logistic regression. No dependency beyond numpy."""
    mu, sd = X.mean(0), X.std(0)
    sd[sd < 1e-8] = 1.0
    Z = (X - mu) / sd
    w = np.zeros(Z.shape[1])
    n = len(y)
    # class weight: breaks are the minority and the costly error
    pos = max(y.sum(), 1.0)
    cw = np.where(y > 0.5, n / (2 * pos), n / (2 * max(n - pos, 1.0)))
    for _ in range(epochs):
        p = 1.0 / (1.0 + np.exp(-Z @ w))
        grad = Z.T @ (cw * (p - y)) / n + l2 * w
        w -= lr * grad
    return np.concatenate([w, mu, sd])


def predict(packed: np.ndarray, X: np.ndarray) -> np.ndarray:
    k = X.shape[1]
    w, mu, sd = packed[:k], packed[k:2 * k], packed[2 * k:]
    Z = (X - mu) / sd
    return 1.0 / (1.0 + np.exp(-Z @ w))


def prf(pred: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
    tp = float(((pred > 0.5) & (y > 0.5)).sum())
    fp = float(((pred > 0.5) & (y < 0.5)).sum())
    fn = float(((pred < 0.5) & (y > 0.5)).sum())
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main() -> int:
    pdfs = sorted(glob.glob(os.path.join(TRAIN_DIR, "*.pdf")))
    if not pdfs:
        print(f"no training documents in {TRAIN_DIR}; run eval/make_synthetic.py first")
        return 1

    per_style: Dict[str, list] = defaultdict(list)
    for pdf in pdfs:
        style = os.path.basename(pdf).rsplit("_", 1)[0]
        per_style[style].append(collect(pdf))
    styles = sorted(per_style)

    print(f"{'held-out style':<16}{'n':>7}{'rules F1':>11}{'learned F1':>13}{'change':>9}")
    print("-" * 58)
    rows = []
    for held in styles:
        tr = [d for s in styles if s != held for d in per_style[s]]
        te = per_style[held]
        Xtr = np.vstack([d[0] for d in tr]); ytr = np.concatenate([d[1] for d in tr])
        Xte = np.vstack([d[0] for d in te]); yte = np.concatenate([d[1] for d in te])
        rte = np.concatenate([d[2] for d in te])
        w = fit(Xtr, ytr)
        f_rule = prf(rte, yte)[2]
        f_lrn = prf(predict(w, Xte), yte)[2]
        rows.append((held, len(yte), f_rule, f_lrn))
        print(f"{held:<16}{len(yte):>7}{f_rule:>11.4f}{f_lrn:>13.4f}"
              f"{f_lrn - f_rule:>+9.4f}")

    mr = float(np.mean([r[2] for r in rows]))
    ml = float(np.mean([r[3] for r in rows]))
    print("-" * 58)
    print(f"{'MEAN':<16}{'':>7}{mr:>11.4f}{ml:>13.4f}{ml - mr:>+9.4f}")

    # Final model on everything, for shipping.
    allX = np.vstack([d[0] for s in styles for d in per_style[s]])
    ally = np.concatenate([d[1] for s in styles for d in per_style[s]])
    w = fit(allX, ally)
    k = allX.shape[1]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({
        "features": FEATURE_NAMES,
        "weights": w[:k].tolist(),
        "mean": w[k:2 * k].tolist(),
        "std": w[2 * k:].tolist(),
        "threshold": 0.5,
        "trained_on": {"documents": len(pdfs), "boundaries": int(len(ally)),
                       "styles": styles},
        "leave_one_style_out": {"rules_f1": round(mr, 4), "learned_f1": round(ml, 4)},
    }, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}  ({os.path.getsize(OUT)} bytes)")

    order = np.argsort(-np.abs(w[:k]))
    print("\nwhat it learned (largest weights first):")
    for i in order[:8]:
        print(f"   {FEATURE_NAMES[i]:<16}{w[i]:>+8.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
