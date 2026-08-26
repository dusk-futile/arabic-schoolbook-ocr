"""Train the post-OCR corrector and measure whether it actually helps.

Trained on this pipeline's own aligned mistakes (eval/pairs.jsonl), and
evaluated on documents held out from training - because a corrector scored on
the errors it was fitted to will always look excellent and tell you nothing.

Two numbers matter and both are reported:
  * how much it lowers word error, and
  * how often it makes a correct word wrong, which is the failure that costs a
    Braille reader something they cannot detect.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mubsir.arabic import canonical, strip_tashkeel
from mubsir.lexicon import Lexicon
from mubsir.ocr_correct import (ConfusionModel, OCRCorrector, is_arabic_word,
                                strip_edges)

PAIRS = "eval/pairs.jsonl"
CORPUS_GLOBS = ["eval/corpus/*.txt", "demo/corpus/*.txt"]


def load_pairs(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def one_to_one(rows: List[dict]) -> List[Tuple[str, str]]:
    """Clean substitutions only: one word read as one other word.

    Insertions and deletions are dropped here. An OCR word with no counterpart
    in the truth is usually page furniture that leaked in, not a letter
    confusion, and training on it would teach the channel nonsense.
    """
    out = []
    for r in rows:
        if len(r["ocr"]) != 1 or len(r["truth"]) != 1:
            continue
        _, o, _ = strip_edges(r["ocr"][0])
        _, t, _ = strip_edges(r["truth"][0])
        if not o or not t or not is_arabic_word(t):
            continue
        if abs(len(o) - len(t)) > 3:
            continue
        out.append((t, o))
    return out


def build_freq() -> Dict[str, int]:
    import glob
    freq: Counter = Counter()
    for pat in CORPUS_GLOBS:
        for f in glob.glob(pat):
            if os.path.basename(f) == "SOURCES.txt":
                continue
            for w in canonical(open(f, encoding="utf-8").read()).split():
                _, core, _ = strip_edges(w)
                if len(core) >= 2 and is_arabic_word(core):
                    freq[strip_tashkeel(core)] += 1
    return dict(freq)


def evaluate(corr: OCRCorrector, rows: List[dict]) -> dict:
    """On held-out error sites: how many did it fix, and how many did it break?"""
    fixed = missed = broken = untouched = 0
    examples: List[str] = []
    for r in rows:
        if len(r["ocr"]) != 1 or len(r["truth"]) != 1:
            continue
        obs, truth = r["ocr"][0], r["truth"][0]
        _, core, _ = strip_edges(obs)
        if not core or not is_arabic_word(core):
            continue
        out, _ = corr.correct_word(obs)
        if out == obs:
            untouched += 1
            continue
        if strip_tashkeel(canonical(out)) == strip_tashkeel(canonical(truth)):
            fixed += 1
            if len(examples) < 8:
                examples.append(f"{obs} -> {out}")
        else:
            broken += 1
            if len(examples) < 12:
                examples.append(f"WRONG {obs} -> {out}  (should be {truth})")
    return {"fixed": fixed, "broken": broken, "untouched": untouched,
            "examples": examples}


def collateral(corr: OCRCorrector, words: List[str]) -> Tuple[int, int]:
    """The important safety number: does it damage words that were already right?"""
    changed = 0
    for w in words:
        out, _ = corr.correct_word(w)
        if out != w:
            changed += 1
    return changed, len(words)


def main() -> int:
    rows = load_pairs(PAIRS)
    if not rows:
        print(f"no pairs at {PAIRS}; run eval/make_pairs.py first")
        return 1

    docs = sorted({r["doc"] for r in rows})
    held = set(docs[::4])            # every fourth document is held out
    train_rows = [r for r in rows if r["doc"] not in held]
    test_rows = [r for r in rows if r["doc"] in held]
    print(f"{len(rows)} error sites across {len(docs)} documents")
    print(f"  train {len(train_rows)}  |  held-out {len(test_rows)} "
          f"({len(held)} documents)")

    pairs = one_to_one(train_rows)
    print(f"  clean one-to-one substitutions for the channel: {len(pairs)}")
    if len(pairs) < 40:
        print("  too few to train a channel; generate more pages first")
        return 1

    conf = ConfusionModel.train(pairs)
    print(f"  learned {len(conf.sub)} character confusions")
    top = sorted(conf.sub.items(), key=lambda kv: kv[1])[:12]
    print("  most likely confusions (lower cost = more common):")
    for k, v in top:
        a, b = k.split(">")
        print(f"     {a or 'ε'} -> {b or 'ε'}   {v:.2f}")

    lex = Lexicon()
    corr = OCRCorrector(lexicon=lex, confusion=conf, freq=build_freq())
    print(f"  frequency prior over {len(corr.freq)} word forms")
    print("  building candidate index ...", end="", flush=True)
    corr.build_index()
    print(" done")

    res = evaluate(corr, test_rows)
    total = res["fixed"] + res["broken"]
    print(f"\nheld-out error sites it acted on: {total}")
    print(f"  fixed   {res['fixed']}")
    print(f"  broken  {res['broken']}")
    print(f"  left alone {res['untouched']}")
    if total:
        print(f"  precision {res['fixed'] / total:.1%}")
    for e in res["examples"][:10]:
        print(f"     {e}")

    # Safety: run it over words that were already correct.
    good = []
    for r in test_rows:
        good.extend(r["truth"])
    good = [w for w in good if is_arabic_word(w)][:1500]
    changed, n = collateral(corr, good)
    print(f"\nsafety: touched {changed} of {n} already-correct words "
          f"({changed / max(n, 1):.2%})")

    path = corr.save()
    print(f"\nwrote {path} ({os.path.getsize(path) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
