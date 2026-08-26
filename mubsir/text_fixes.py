"""Character-level repairs that are safe enough to apply unattended.

Every fix here clears a hard bar: measured on 1,533 words that were already
correct, it must damage **under 0.5%** of them. That threshold is not arbitrary
- it is the point below which a correction pass stops paying for itself at this
pipeline's error rate, and a fuller word-level corrector was built, measured
against it, and dropped for failing it (it broke sixteen correct words for
every five it fixed). What survives is only what earns its place:

    character look-alikes            0.33% damage
    word-final hamza for a comma     0.00% damage

The mappings were not guessed. They came out of a confusion model trained on
this pipeline's own aligned mistakes, which also showed where the error really
is: **62.9% of all character errors are punctuation**, and the Arabic comma
alone is 31% of them - read as a full stop 210 times, as hamza 128, as a Latin
comma 98, as a semicolon 83. Only the unambiguous member of that family is
repaired here.
"""
from __future__ import annotations

from typing import Tuple

ARABIC_LO, ARABIC_HI = 0x0600, 0x06FF
_PUNCT = "«»\"'()[]{}،.:؛؟!-–—…,;?"

# Characters that do not occur in correctly-typed Arabic, so emitting one is
# always a misread of its Arabic look-alike.
#
# The confusion model reports P(observed | truth), and reading it backwards is
# an easy and costly mistake: it also lists Greek letters being read as digits,
# but that is truth-Greek misread as digits, so "fixing" Greek to digits would
# destroy the genuine Greek in an academic Arabic text (this corpus contains
# λογία). Only mappings whose SOURCE cannot legitimately appear are listed.
ALWAYS_FIX = {
    "ک": "ك",   # Persian kaf      -> Arabic kaf
    "ی": "ى",   # Persian yeh      -> alef maqsura
    "ھ": "ه",   # heh doachashmee  -> heh
}


def is_arabic_word(word: str) -> bool:
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters
               if ARABIC_LO <= ord(c) <= ARABIC_HI) >= len(letters) * 0.6


def strip_edges(word: str) -> Tuple[str, str, str]:
    """Split a token into (leading punctuation, core, trailing punctuation)."""
    i, j = 0, len(word)
    while i < j and word[i] in _PUNCT:
        i += 1
    while j > i and word[j - 1] in _PUNCT:
        j -= 1
    return word[:i], word[i:j], word[j:]


def fix_characters(text: str) -> str:
    for bad, good in ALWAYS_FIX.items():
        if bad in text:
            text = text.replace(bad, good)
    return text


def fix_comma_lookalikes(text: str, lexicon) -> Tuple[str, int]:
    """Word-final hamza where an Arabic comma belongs.

    'عنها،' comes back as 'عنهاء'. Repaired only when dropping the mark leaves a
    real word and keeping it does not, so a genuine word-final hamza - 'شيء',
    'الماء' - is never touched. A word-final full stop is deliberately left
    alone: unlike a stray hamza, it is very often correct.
    """
    if lexicon is None or not getattr(lexicon, "words", None):
        return text, 0
    out, fixed = [], 0
    for token in text.split(" "):
        lead, core, _ = strip_edges(token)
        if (len(core) > 2 and core[-1] == "ء" and is_arabic_word(core)
                and not lexicon.contains(core) and lexicon.contains(core[:-1])):
            # The mark being repaired IS the punctuation, so any trailing
            # punctuation the tokeniser split off is dropped rather than kept.
            out.append(lead + core[:-1] + "،")
            fixed += 1
        else:
            out.append(token)
    return " ".join(out), fixed
