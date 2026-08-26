"""Deterministic Arabic text normalisation.

Two distinct levels, and the distinction matters:

``canonical``  Safe for output. Repairs *encoding* damage (presentation forms,
               ligatures, broken spacing) but never destroys orthography.
               A Braille reader reads real Arabic: collapsing أ/إ/آ into ا
               would silently corrupt the book.

``search``     Aggressive, lossy. Used ONLY for comparing two strings during
               evaluation and dictionary lookup. Never written to output.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

# ---------------------------------------------------------------- code points
TATWEEL = "ـ"
ZWJ, ZWNJ = "‍", "‌"

# Tashkeel / harakat. Kept or stripped by policy, never silently.
TASHKEEL = (
    "ًٌٍَُِّْٕٓٔ"
    "ٰٖٜٟٗ٘ٙٚٛٝٞ"
)
TASHKEEL_RE = re.compile(f"[{TASHKEEL}]")

# Bidi + invisible formatting controls. These are pure poison downstream:
# an embosser or Word will happily render them as boxes or reorder a line.
BIDI_CONTROLS = "‎‏‪‫‬‭‮⁦⁧⁨⁩؜"
INVISIBLE_RE = re.compile(f"[{BIDI_CONTROLS}​﻿­⁠]")

ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
EXT_ARABIC_INDIC = "۰۱۲۳۴۵۶۷۸۹"
WESTERN = "0123456789"

# Terminal punctuation - a strong paragraph-end signal.
TERMINAL_PUNCT = ".!?؟۔:؛"  # . ! ? ؟ ۔ : ؛

_PUNCT_MAP = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ",
}


def _ranges(ch: str) -> str:
    o = ord(ch)
    if 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0x08A0 <= o <= 0x08FF:
        return "arabic"
    if 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
        return "presentation"
    if ch.isspace():
        return "space"
    if o < 0x80:
        return "ascii"
    if 0x2000 <= o <= 0x206F:
        return "punct_general"
    return "foreign"


def char_profile(text: str) -> Counter:
    """Histogram of character classes. Feeds the text-layer trust check."""
    return Counter(_ranges(c) for c in text)


def strip_invisible(text: str) -> str:
    return INVISIBLE_RE.sub("", text)


def unshape(text: str) -> str:
    """Presentation forms -> base letters; lam-alef ligatures decomposed.

    NFKC does the heavy lifting: U+FEFB (ﻻ) decomposes to ل+ا, and every
    contextual form (initial/medial/final/isolated) maps back to its base
    letter. This is the single highest-value repair for Arabic PDFs, whose
    text layers are very often stored as shaped glyphs.
    """
    if not text:
        return text
    return unicodedata.normalize("NFKC", text)


def strip_tashkeel(text: str) -> str:
    return TASHKEEL_RE.sub("", text)


def tashkeel_ratio(text: str) -> float:
    letters = sum(1 for c in text if 0x0621 <= ord(c) <= 0x064A)
    if not letters:
        return 0.0
    return len(TASHKEEL_RE.findall(text)) / letters


def convert_digits(text: str, policy: str = "keep") -> str:
    """policy: keep | western | arabic_indic"""
    if policy == "keep":
        return text
    if policy == "western":
        table = {ord(a): w for a, w in zip(ARABIC_INDIC, WESTERN)}
        table.update({ord(a): w for a, w in zip(EXT_ARABIC_INDIC, WESTERN)})
        return text.translate(table)
    if policy == "arabic_indic":
        return text.translate({ord(w): a for w, a in zip(WESTERN, ARABIC_INDIC)})
    raise ValueError(f"unknown digit policy: {policy}")


_ARABIC_CTX = r"[؀-ۿ]"
_LATIN_TO_ARABIC_PUNCT = [
    (re.compile(rf"(?<={_ARABIC_CTX})\s*,(?=\s|$|{_ARABIC_CTX})"), "،"),
    (re.compile(rf"(?<={_ARABIC_CTX})\s*;(?=\s|$|{_ARABIC_CTX})"), "؛"),
    (re.compile(rf"(?<={_ARABIC_CTX})\s*\?(?=\s|$|{_ARABIC_CTX})"), "؟"),
]


def arabize_punctuation(text: str) -> str:
    """Latin comma/semicolon/question mark -> their Arabic forms, in Arabic context.

    Recognisers routinely emit ',' for '،' because the shapes are close. Only
    marks with an Arabic letter on the left and Arabic (or nothing) on the
    right are converted, so an English citation inside the same paragraph keeps
    its own punctuation.
    """
    for pattern, repl in _LATIN_TO_ARABIC_PUNCT:
        text = pattern.sub(repl, text)
    return text


def fix_punct_spacing(text: str) -> str:
    """Arabic punctuation hugs the preceding word and takes one space after."""
    text = re.sub(r"\s+([،؛؟!\.:\)\]»])", r"\1", text)
    text = re.sub(r"([،؛؟!:])(?=\S)", r"\1 ", text)
    text = re.sub(r"([\(\[«])\s+", r"\1", text)
    text = re.sub(r"\s+([\(\[«])", r" \1", text)
    return text


def canonical(
    text: str,
    *,
    keep_tashkeel: bool = True,
    digits: str = "keep",
    remove_tatweel: bool = True,
) -> str:
    """Output-safe normalisation. Repairs encoding, preserves orthography."""
    if not text:
        return ""
    text = unshape(text)
    text = strip_invisible(text)
    for src, dst in _PUNCT_MAP.items():
        text = text.replace(src, dst)
    if remove_tatweel:
        text = text.replace(TATWEEL, "")
    text = text.replace(ZWJ, "").replace(ZWNJ, "")
    if not keep_tashkeel:
        text = strip_tashkeel(text)
    text = convert_digits(text, digits)
    text = re.sub(r"[ \t　]+", " ", text)
    text = arabize_punctuation(text)
    text = fix_punct_spacing(text)
    return text.strip()


_ALEF_RE = re.compile("[آأإٱٲٳ]")


def search_form(text: str) -> str:
    """Lossy. For string comparison only - NEVER write this to a document."""
    text = canonical(text, keep_tashkeel=False, digits="western")
    text = _ALEF_RE.sub("ا", text)
    text = text.replace("ى", "ي")      # alef maqsura -> ya
    text = text.replace("ة", "ه")      # ta marbuta  -> ha
    text = text.replace("ؤ", "و").replace("ئ", "ي")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def looks_arabic(text: str, threshold: float = 0.5) -> bool:
    p = char_profile(text)
    scripted = p["arabic"] + p["presentation"] + p["ascii"] + p["foreign"]
    if scripted == 0:
        return False
    return (p["arabic"] + p["presentation"]) / scripted >= threshold
