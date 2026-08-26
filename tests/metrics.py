"""Metrics. Every number in RESEARCH.md and the README comes from here."""
from __future__ import annotations

import unicodedata
from typing import List, Sequence, Tuple


def levenshtein(a: Sequence, b: Sequence) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    ref = unicodedata.normalize("NFC", ref)
    hyp = unicodedata.normalize("NFC", hyp)
    if not ref:
        return 0.0 if not hyp else 1.0
    return levenshtein(ref, hyp) / len(ref)


def wer(ref: str, hyp: str) -> float:
    r, h = ref.split(), hyp.split()
    if not r:
        return 0.0 if not h else 1.0
    return levenshtein(r, h) / len(r)


def prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def boundary_scores(gold_ids: List[int], pred_ids: List[int]):
    """Paragraph-boundary agreement over the gaps between consecutive lines.

    Compares *breaks*, not paragraph identity, because that is the decision the
    embosser actually cares about: at this line gap, new paragraph or not?
    """
    assert len(gold_ids) == len(pred_ids)
    tp = fp = fn = tn = 0
    errors = []
    for i in range(len(gold_ids) - 1):
        g = gold_ids[i] != gold_ids[i + 1]
        p = pred_ids[i] != pred_ids[i + 1]
        if g and p:
            tp += 1
        elif p and not g:
            fp += 1
            errors.append((i, "false-break"))
        elif g and not p:
            fn += 1
            errors.append((i, "missed-break"))
        else:
            tn += 1
    prec, rec, f1 = prf(tp, fp, fn)
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": prec, "recall": rec, "f1": f1,
        "n_gaps": len(gold_ids) - 1, "errors": errors,
    }


def hallucination_rate(ref: str, hyp: str) -> float:
    """Share of output words with no counterpart in the source.

    Deliberately crude and deliberately strict: a Braille reader cannot detect
    an invented word, so this metric is allowed to over-report, never under.
    """
    from mubsir.arabic import search_form
    ref_words = set(search_form(ref).split())
    hyp_words = search_form(hyp).split()
    if not hyp_words:
        return 0.0
    unseen = sum(1 for w in hyp_words if w not in ref_words)
    return unseen / len(hyp_words)


def reading_order_accuracy(seq) -> float:
    """Share of paragraph pairs that come out in the right relative order.

    Boundary F1 only asks "is there a break here", so a page whose columns are
    read interleaved can still score well on it while being unreadable. This
    measures the other half: given the gold paragraph id of each line in the
    order the pipeline emitted them, how often is an earlier paragraph actually
    emitted before a later one. 1.0 means perfect reading order.
    """
    seq = [s for s in seq if s is not None]
    n = len(seq)
    if n < 2:
        return 1.0
    total = n * (n - 1) // 2
    inversions = 0
    for i in range(n):
        si = seq[i]
        for j in range(i + 1, n):
            if seq[j] < si:
                inversions += 1
    return 1.0 - inversions / total
