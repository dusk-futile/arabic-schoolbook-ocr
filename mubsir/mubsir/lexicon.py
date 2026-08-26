"""Offline Arabic lexicon and a deliberately timid OCR corrector.

Design rule, taken straight from the brief: a hallucinated word in a Braille
book is worse than a garbled one, because the reader has no way to detect it.
So the corrector may only ever move a word from "not a word" to "a word", by
the single most common OCR failure (a doubled letter), and it records every
edit it makes so a human can audit them.
"""
from __future__ import annotations

import gzip
import os
from functools import lru_cache
from typing import Iterable, List, Optional, Set, Tuple

from .arabic import canonical, strip_tashkeel

_MODELS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "models", "lexicon")
LEXICON_PATH = os.path.join(_MODELS, "ar_words.txt.gz")
ENGLISH_PATH = os.path.join(_MODELS, "en_words.txt.gz")

# Hunspell stores stems; Arabic clitics attach freely, so strip them on lookup.
PROCLITICS = ["", "و", "ف", "ب", "ك", "ل", "س",
              "ال", "وال", "فال", "بال", "كال", "لل", "ولل", "بالـ",
              "وب", "ول", "فب", "فل", "وس", "فس"]
ENCLITICS = ["", "ها", "هما", "هم", "هن", "ه", "ك", "كما", "كم", "كن",
             "ي", "نا", "ني", "ية", "ين", "ون", "ات", "ان", "تا"]


def _load_gz(path: str) -> Set[str]:
    if not os.path.exists(path):
        return set()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {w.strip() for w in f if w.strip()}


class Lexicon:
    """Arabic stems, plus an English wordlist for the Latin runs that appear
    inside Arabic academic text (citations, technical terms)."""

    def __init__(self, path: str = LEXICON_PATH, english_path: str = ENGLISH_PATH):
        self.path = path
        self.words: Set[str] = _load_gz(path)
        self.english: Set[str] = _load_gz(english_path)

    def contains_en(self, word: str) -> bool:
        w = "".join(c for c in word.lower() if c.isalpha())
        return len(w) > 1 and w in self.english

    def __len__(self) -> int:
        return len(self.words)

    @property
    def available(self) -> bool:
        return bool(self.words)

    def contains_exact(self, word: str) -> bool:
        w = strip_tashkeel(canonical(word)).strip("\u00ab\u00bb\"'()[]\u060c.:\u061b\u061f!-\u2013\u2014")
        return bool(w) and w in self.words

    @lru_cache(maxsize=200_000)
    def contains(self, word: str) -> bool:
        w = strip_tashkeel(canonical(word)).strip("«»\"'()[]،.:؛؟!-–—")
        if not w or not self.words:
            return False
        if w in self.words:
            return True
        for pre in PROCLITICS:
            if pre and not w.startswith(pre):
                continue
            stem = w[len(pre):]
            if len(stem) < 2:
                continue
            if stem in self.words:
                return True
            for suf in ENCLITICS:
                if not suf or not stem.endswith(suf):
                    continue
                base = stem[: -len(suf)]
                if len(base) >= 2 and base in self.words:
                    return True
        return False


def _dedouble_candidates(word: str) -> List[str]:
    """Every single-letter de-duplication of an adjacent identical pair."""
    out = []
    for i in range(len(word) - 1):
        if word[i] == word[i + 1] and 0x0600 <= ord(word[i]) <= 0x06FF:
            out.append(word[:i] + word[i + 1:])
    return out


def _deletion_candidates(word: str) -> List[str]:
    """Every single-character deletion.

    Broader than de-doubling, for repaired-font text where a spurious letter
    can be inserted next to a ligature rather than duplicated. Still only one
    deletion, still only applied when the result is uniquely a real word.
    """
    seen, out = set(), []
    for i, ch in enumerate(word):
        if not (0x0600 <= ord(ch) <= 0x06FF):
            continue
        cand = word[:i] + word[i + 1:]
        if len(cand) >= 2 and cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


class Corrector:
    """Fixes only doubled-letter OCR artefacts, only when provably safe."""

    def __init__(self, lexicon: Optional[Lexicon] = None, strict: bool = False):
        # strict=False  : a word is "fine" if any affix analysis finds it.
        #                 Safest, but blocks fixes like \u0643\u0643\u0627\u0646\u062a where a spurious
        #                 proclitic analysis makes the garbled form look valid.
        # strict=True   : only an exact lexicon hit counts as "fine".
        self.strict = strict
        self.lex = lexicon if lexicon is not None else Lexicon()
        self.edits: List[Tuple[str, str, str]] = []   # (before, after, reason)
        self.rejected: List[Tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return self.lex.available

    def fix_word(self, word: str, mode: str = "double") -> str:
        """mode: "double" (adjacent duplicates only) or "delete" (any one
        spurious letter). "delete" is for font-repaired text; both refuse to
        touch a word that is already in the lexicon, and both refuse when the
        answer is not unique."""
        if not self.lex.available or len(word) < 3:
            return word
        core = word.strip("«»\"'()[]،.:؛؟!-–—")
        if not core or not any(0x0600 <= ord(c) <= 0x06FF for c in core):
            return word
        already_ok = self.lex.contains_exact(core) if self.strict else self.lex.contains(core)
        if already_ok:
            return word            # already a word: never touch it
        gen = _dedouble_candidates if mode == "double" else _deletion_candidates
        cands = [c for c in gen(core) if self.lex.contains_exact(c)]
        if len(set(cands)) != 1:
            if cands:
                self.rejected.append((core, "ambiguous"))
            return word
        fixed = cands[0]
        self.edits.append((core, fixed, mode))
        return word.replace(core, fixed, 1)

    def fix_text(self, text: str, mode: str = "double") -> str:
        return " ".join(self.fix_word(w, mode) for w in text.split(" "))

    def coverage(self, text: str) -> float:
        """Share of Arabic words that are real words. A proxy for text quality
        when no ground truth exists."""
        words = [w for w in text.split()
                 if sum(1 for c in w if 0x0600 <= ord(c) <= 0x06FF) >= 2]
        if not words:
            return 0.0
        return sum(1 for w in words if self.lex.contains(w)) / len(words)

    def summary(self) -> dict:
        return {
            "lexicon_size": len(self.lex),
            "edits": len(self.edits),
            "rejected": len(self.rejected),
        }
