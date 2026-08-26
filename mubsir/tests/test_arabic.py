"""Normalisation must never damage orthography, and must repair encoding."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
import pytest
from mubsir.arabic import (canonical, search_form, unshape, strip_tashkeel,
                           convert_digits, arabize_punctuation, char_profile)


def test_presentation_forms_become_base_letters():
    shaped = "ﻟﻠﺤ"          # lam, lam, ha in contextual forms
    out = unshape(shaped)
    assert all(0x0600 <= ord(c) <= 0x06FF for c in out)


def test_lam_alef_ligature_decomposes():
    assert unshape("ﻻ") == "لا"
    assert unshape("ﻷ") == "لأ"


def test_canonical_preserves_hamza_orthography():
    # Collapsing أ/إ/آ into ا would silently corrupt a Braille book.
    for w in ["أحمد", "إبراهيم", "آمن", "مسؤول", "شيء"]:
        assert canonical(w) == w


def test_canonical_keeps_tashkeel_by_default():
    assert "َ" in canonical("مَدرسة")
    assert "َ" not in canonical("مَدرسة", keep_tashkeel=False)


def test_tatweel_removed():
    assert canonical("مـــدرسة") == "مدرسة"


def test_bidi_controls_stripped():
    assert canonical("‎مرحبا‫") == "مرحبا"


def test_search_form_is_lossy_and_never_used_for_output():
    assert search_form("الأصيلة") == search_form("الاصيله")
    assert canonical("الأصيلة") != canonical("الاصيله")   # output stays distinct


def test_digit_policies():
    assert convert_digits("صفحة ١٢٣", "western") == "صفحة 123"
    assert convert_digits("page 123", "arabic_indic") == "page ١٢٣"
    assert convert_digits("١٢٣", "keep") == "١٢٣"


def test_arabize_punctuation_only_in_arabic_context():
    assert arabize_punctuation("تحيز, وبالمثل") == "تحيز، وبالمثل"
    assert arabize_punctuation("Smith, J. and Jones") == "Smith, J. and Jones"


def test_char_profile_flags_broken_cmap():
    good = char_profile("الإبداع قدرة عقلية")
    assert good["foreign"] == 0
    bad = char_profile("اƾبداع عقǁية")       # Latin-Extended where Arabic belongs
    assert bad["foreign"] > 0
