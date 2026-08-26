"""Trained post-OCR correction for Arabic, with one narrow job.

The job: given a word the recogniser produced, decide whether it is a real word
and, if not, what it should have been. Nothing else. It never rewrites a
sentence, never reorders anything, and never proposes a word that is not
already in the dictionary - so it can fix a misreading but cannot invent a
term that was never on the page.

It is a noisy channel. For an observed word `o`, the best correction is the
candidate `c` maximising

    P(c | o)  ∝  P(o | c) · P(c)

where P(o|c) comes from a **confusion model learned from this pipeline's own
mistakes** - which letters this recogniser actually confuses, how often it
drops a mark, where it splits a shape - and P(c) is a word-frequency prior.
Learning the channel from the real system matters: a generic edit-distance
model treats ط→ص and ط→ك as equally likely, when in practice one is common and
the other never happens.

Candidates come from the dictionary only, via three routes:

  1. an exact hit, in which case the word is left alone;
  2. an orthographic-variant hit (the alef/ya/ta-marbuta family), which is by
     far the largest error class in Arabic OCR;
  3. a deletion index, giving every dictionary word within a small edit
     distance without scanning 294,000 entries.

A correction is applied only when it wins by a clear margin, and every edit is
recorded so a human can audit the whole set in one pass.
"""
from __future__ import annotations

import gzip
import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .arabic import canonical, search_form, strip_tashkeel

from .paths import MODELS_DIR

MODEL_PATH = os.path.join(MODELS_DIR, "ocr_correct.json.gz")

ARABIC_LO, ARABIC_HI = 0x0600, 0x06FF
MAX_EDITS = 2
MIN_LEN = 3


def is_arabic_word(w: str) -> bool:
    letters = [c for c in w if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if ARABIC_LO <= ord(c) <= ARABIC_HI) >= len(letters) * 0.6


def is_latin_word(w: str) -> bool:
    letters = [c for c in w if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if ord(c) < 0x0250) >= len(letters) * 0.6


def strip_edges(w: str) -> Tuple[str, str, str]:
    """Split a token into (leading punctuation, core, trailing punctuation)."""
    i, j = 0, len(w)
    punct = "«»\"'()[]{}،.:؛؟!-–—…,;?"
    while i < j and w[i] in punct:
        i += 1
    while j > i and w[j - 1] in punct:
        j -= 1
    return w[:i], w[i:j], w[j:]


# --------------------------------------------------------------- alignment
def align_chars(a: str, b: str) -> List[Tuple[str, str]]:
    """Character alignment via Levenshtein backtrace.

    Returns (from, to) pairs where "" marks an insertion or a deletion, which
    is what the confusion counts are built from.
    """
    n, m = len(a), len(b)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    out: List[Tuple[str, str]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (a[i - 1] != b[j - 1]):
            out.append((a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            out.append((a[i - 1], ""))
            i -= 1
        else:
            out.append(("", b[j - 1]))
            j -= 1
    return list(reversed(out))


@dataclass
class ConfusionModel:
    """Learned P(observed char | true char), as negative log costs."""
    sub: Dict[str, float] = field(default_factory=dict)     # "t>o" -> cost
    default_sub: float = 4.0
    default_ins: float = 4.5
    default_del: float = 4.5
    trained_on: int = 0

    def cost(self, true_ch: str, obs_ch: str) -> float:
        if true_ch == obs_ch:
            return 0.0
        key = f"{true_ch}>{obs_ch}"
        if key in self.sub:
            return self.sub[key]
        if not true_ch:
            return self.default_ins
        if not obs_ch:
            return self.default_del
        return self.default_sub

    def distance(self, true_w: str, obs_w: str, ceiling: float = 12.0) -> float:
        """Weighted edit distance under the learned channel."""
        n, m = len(true_w), len(obs_w)
        prev = [0.0] * (m + 1)
        for j in range(1, m + 1):
            prev[j] = prev[j - 1] + self.cost("", obs_w[j - 1])
        for i in range(1, n + 1):
            cur = [prev[0] + self.cost(true_w[i - 1], "")]
            for j in range(1, m + 1):
                cur.append(min(
                    prev[j] + self.cost(true_w[i - 1], ""),
                    cur[j - 1] + self.cost("", obs_w[j - 1]),
                    prev[j - 1] + self.cost(true_w[i - 1], obs_w[j - 1]),
                ))
            if min(cur) > ceiling:
                return ceiling + 1.0
            prev = cur
        return prev[m]

    # ------------------------------------------------------------- training
    @classmethod
    def train(cls, pairs: Iterable[Tuple[str, str]], smoothing: float = 0.6) -> "ConfusionModel":
        sub_counts: Dict[str, Counter] = defaultdict(Counter)
        total: Counter = Counter()
        n = 0
        for truth, obs in pairs:
            if not truth or not obs:
                continue
            n += 1
            for t_ch, o_ch in align_chars(truth, obs):
                sub_counts[t_ch][o_ch] += 1
                total[t_ch] += 1
        costs: Dict[str, float] = {}
        for t_ch, obs in sub_counts.items():
            denom = total[t_ch] + smoothing * (len(obs) + 1)
            for o_ch, c in obs.items():
                if t_ch == o_ch:
                    continue
                p = (c + smoothing) / denom
                costs[f"{t_ch}>{o_ch}"] = round(-math.log(p), 4)
        return cls(sub=costs, trained_on=n)


# ------------------------------------------------------------------ index
def deletions(word: str, k: int) -> Iterable[str]:
    """All strings obtainable by deleting up to k characters (SymSpell style).

    Two words within edit distance k share at least one deletion variant, so
    this turns candidate lookup into a dictionary hit instead of a scan over
    294,000 entries.
    """
    seen = {word}
    frontier = {word}
    for _ in range(k):
        nxt = set()
        for w in frontier:
            for i in range(len(w)):
                d = w[:i] + w[i + 1:]
                if len(d) >= 2 and d not in seen:
                    seen.add(d)
                    nxt.add(d)
        frontier = nxt
    return seen


@dataclass
class OCRCorrector:
    lexicon: object = None
    confusion: ConfusionModel = field(default_factory=ConfusionModel)
    freq: Dict[str, int] = field(default_factory=dict)
    max_edits: int = MAX_EDITS
    min_margin: float = 1.2          # winner must beat runner-up by this much
    max_cost: float = 9.0            # beyond this the candidate is not credible
    edits: List[tuple] = field(default_factory=list)
    skipped: List[tuple] = field(default_factory=list)
    _del_index: Dict[str, List[str]] = field(default_factory=dict)
    _variant_index: Dict[str, List[str]] = field(default_factory=dict)

    # ------------------------------------------------------------- indexes
    def build_index(self, max_words: Optional[int] = None) -> None:
        if not self.lexicon or not getattr(self.lexicon, "words", None):
            return
        words = self.lexicon.words
        if max_words:
            words = set(list(words)[:max_words])
        var: Dict[str, List[str]] = defaultdict(list)
        dele: Dict[str, List[str]] = defaultdict(list)
        for w in words:
            var[search_form(w)].append(w)
            for d in deletions(w, 1):
                dele[d].append(w)
        self._variant_index = dict(var)
        self._del_index = dict(dele)

    @property
    def ready(self) -> bool:
        return bool(self._variant_index or self._del_index)

    # ------------------------------------------------------------ scoring
    def _prior(self, word: str) -> float:
        f = self.freq.get(word) or self.freq.get(strip_tashkeel(word), 0)
        return math.log(f + 1.0)

    def candidates(self, word: str) -> List[str]:
        out = set()
        sf = search_form(word)
        out.update(self._variant_index.get(sf, []))
        for d in deletions(word, 1):
            out.update(self._del_index.get(d, []))
        out.update(self._del_index.get(word, []))
        out.discard(word)
        return [c for c in out if abs(len(c) - len(word)) <= self.max_edits]

    def correct_word(self, token: str) -> Tuple[str, str]:
        """Returns (token, reason). The token is unchanged unless a candidate wins."""
        lead, core, trail = strip_edges(token)
        if len(core) < MIN_LEN or not is_arabic_word(core):
            return token, ""
        if not self.ready or self.lexicon is None:
            return token, ""
        if self.lexicon.contains(core):
            return token, "already-a-word"

        scored: List[Tuple[float, str]] = []
        for cand in self.candidates(core):
            cost = self.confusion.distance(cand, core, ceiling=self.max_cost)
            if cost > self.max_cost:
                continue
            scored.append((cost - 0.35 * self._prior(cand), cand))
        if not scored:
            self.skipped.append((core, "no-candidate"))
            return token, ""
        scored.sort()
        best, runner = scored[0], (scored[1] if len(scored) > 1 else None)
        if runner is not None and (runner[0] - best[0]) < self.min_margin:
            self.skipped.append((core, f"ambiguous:{best[1]}|{runner[1]}"))
            return token, ""
        self.edits.append((core, best[1], round(best[0], 2)))
        return lead + best[1] + trail, "corrected"

    def correct_text(self, text: str) -> str:
        return " ".join(self.correct_word(t)[0] for t in text.split(" "))

    # ------------------------------------------------------- persistence
    def save(self, path: str = MODEL_PATH) -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        blob = {
            "confusion": {"sub": self.confusion.sub,
                          "default_sub": self.confusion.default_sub,
                          "default_ins": self.confusion.default_ins,
                          "default_del": self.confusion.default_del,
                          "trained_on": self.confusion.trained_on},
            "freq": self.freq,
            "params": {"max_edits": self.max_edits, "min_margin": self.min_margin,
                       "max_cost": self.max_cost},
        }
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(blob, f, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, lexicon=None, path: str = MODEL_PATH) -> "OCRCorrector":
        obj = cls(lexicon=lexicon)
        if os.path.exists(path):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as f:
                    blob = json.load(f)
                c = blob.get("confusion", {})
                obj.confusion = ConfusionModel(
                    sub=c.get("sub", {}),
                    default_sub=c.get("default_sub", 4.0),
                    default_ins=c.get("default_ins", 4.5),
                    default_del=c.get("default_del", 4.5),
                    trained_on=c.get("trained_on", 0))
                obj.freq = blob.get("freq", {})
                p = blob.get("params", {})
                obj.max_edits = p.get("max_edits", MAX_EDITS)
                obj.min_margin = p.get("min_margin", 1.2)
                obj.max_cost = p.get("max_cost", 9.0)
            except Exception:
                pass
        return obj

    def summary(self) -> dict:
        return {"edits": len(self.edits), "skipped": len(self.skipped),
                "confusions_learned": len(self.confusion.sub),
                "vocab": len(self.freq)}

# --------------------------------------------------------- character fixes
# Characters that do not occur in correctly-typed Arabic text, so emitting one
# is always a misread of its Arabic look-alike. Surfaced by the learned
# confusion model rather than guessed.
#
# The confusion model reports P(observed | truth), and reading it in the wrong
# direction is an easy and costly mistake: it also lists Greek letters being
# read as digits, but that is truth-Greek misread as digits, so "fixing"
# Greek to digits would destroy the genuine Greek in an academic Arabic text
# (this corpus contains \u03bb\u03bf\u03b3\u03af\u03b1). Only mappings whose SOURCE cannot legitimately
# appear are listed here.
ALWAYS_FIX = {
    "\u06a9": "\u0643",   # Persian kaf        -> Arabic kaf
    "\u06cc": "\u0649",   # Persian yeh        -> alef maqsura
    "\u06be": "\u0647",   # heh doachashmee    -> heh
    "\u064a\u0654": "\u0626",   # yeh + hamza above -> yeh with hamza
}

# Marks the recogniser confuses with the Arabic comma. It is the single largest
# error source in this pipeline - the Arabic comma alone accounts for about a
# third of all character errors - because the glyphs are small and sit on the
# baseline. Only the unambiguous member of the family is repaired: a word-final
# hamza after an otherwise complete word is not Arabic, whereas a word-final
# full stop very often is, so '.' is deliberately left alone.
COMMA_LOOKALIKES = "\u0621"        # hamza only


def fix_characters(text: str) -> str:
    for bad, good in ALWAYS_FIX.items():
        if bad in text:
            text = text.replace(bad, good)
    return text


def fix_comma_lookalikes(text: str, lexicon) -> Tuple[str, int]:
    """Word-final hamza where an Arabic comma belongs.

    'عنها،' is read as 'عنهاء'. Repaired only when dropping the mark leaves a
    real word and keeping it does not, so a genuine word-final hamza (like
    'شيء') is never touched.
    """
    if lexicon is None or not getattr(lexicon, "words", None):
        return text, 0
    out, n = [], 0
    for tok in text.split(" "):
        lead, core, trail = strip_edges(tok)
        if (len(core) > 2 and core[-1] in COMMA_LOOKALIKES
                and is_arabic_word(core)
                and not lexicon.contains(core)
                and lexicon.contains(core[:-1])):
            # the mark being repaired IS the punctuation, so any trailing
            # punctuation the tokeniser split off is dropped rather than kept
            out.append(lead + core[:-1] + "\u060c")
            n += 1
        else:
            out.append(tok)
    return " ".join(out), n
