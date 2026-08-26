"""Embedded Latin inside Arabic lines.

Arabic academic books quote English terms and cite Latin titles, and the two
scripts need different recognisers: Tesseract's `ara` model has no Latin
characters in its alphabet at all, so it *cannot* emit an English word, while
`ara+eng` reads Latin but degrades Arabic. Each line is therefore read twice
and arbitrated per word.

The arbitration is what these tests pin down. A dictionary check alone is not
enough - Arabic pushed through an English model lands on short English words
constantly - so the decision rests on the confidence margin between the two
readings.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from mubsir.lexicon import Lexicon


def _merger():
    """A HybridEngine instance with only the arbitration wired up.

    Built without __init__ so the test needs neither Tesseract nor the
    detection model - it is exercising the decision, not the recognisers.
    """
    from mubsir.ocr.hybrid import HybridEngine
    eng = HybridEngine.__new__(HybridEngine)
    eng._lex = Lexicon()
    eng.latin_swaps = 0
    return eng


def word(text, left, conf, top=100, width=90, height=30):
    return {"text": text, "conf": conf, "left": left, "top": top,
            "width": width, "height": height}


needs_lexicon = pytest.mark.skipif(
    not Lexicon().english, reason="English wordlist not downloaded")


@needs_lexicon
def test_confident_latin_replaces_arabic_garbage():
    eng = _merger()
    # 'ara' cannot spell Latin, so a Latin run comes back as low-confidence junk
    arabic = [word("لا09ا05/000", 100, 0.44)]
    latin = [word("Psychology", 100, 0.95)]
    out = eng._merge_latin(arabic, latin)
    assert out[0]["text"] == "Psychology"


@needs_lexicon
def test_real_arabic_is_never_overwritten_by_low_confidence_latin():
    eng = _merger()
    # These are the actual false positives seen on a real page.
    for ar_text, ar_conf, lat_text, lat_conf in [
        ("الثانوية", 0.93, "Goll", 0.01),
        ("جوسالا", 0.89, "Yoga", 0.20),
        ("رورشاخ", 0.91, "Flag", 0.03),
        ("إكسنر", 0.90, "sus", 0.24),
    ]:
        out = eng._merge_latin([word(ar_text, 100, ar_conf)],
                               [word(lat_text, 100, lat_conf)])
        assert out[0]["text"] == ar_text, f"{ar_text} was overwritten by {lat_text}"


@needs_lexicon
def test_proper_nouns_pass_on_confidence_without_a_dictionary_hit():
    eng = _merger()
    # "Psichiologia" is in no English wordlist; the margin has to carry it.
    out = eng._merge_latin([word("05006", 100, 0.30)],
                           [word("Psichiologia", 100, 0.93)])
    assert out[0]["text"] == "Psichiologia"


@needs_lexicon
def test_candidate_must_sit_on_the_same_row():
    eng = _merger()
    # Both passes read one stacked canvas, so x-overlap alone pairs words from
    # different lines. This was a real bug: it cut Latin recovery to 6%.
    arabic = [word("لا09ا05/000", 100, 0.44, top=100)]
    latin = [word("Psychology", 100, 0.95, top=400)]
    out = eng._merge_latin(arabic, latin)
    assert out[0]["text"] == "لا09ا05/000"


@needs_lexicon
def test_arabic_that_is_a_real_word_is_left_alone():
    eng = _merger()
    out = eng._merge_latin([word("الكتاب", 100, 0.40)],
                           [word("Psychology", 100, 0.99)])
    assert out[0]["text"] == "الكتاب"


@needs_lexicon
def test_non_latin_candidate_is_rejected():
    eng = _merger()
    out = eng._merge_latin([word("لا09ا05", 100, 0.30)],
                           [word("١٢٣٤", 100, 0.99)])
    assert out[0]["text"] == "لا09ا05"
