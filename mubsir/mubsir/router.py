"""Decide, per page, whether to trust the PDF text layer or run OCR.

Arabic makes this decision genuinely load-bearing. Publishers' PDFs often
carry a text layer built from shaped presentation glyphs with a broken
ToUnicode map, so extraction returns confident-looking mojibake. Trusting it
would put garbage into a Braille book; OCRing a good text layer would throw
away a perfect transcript. So the test is on the *content*, not on whether a
text layer merely exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .model import Line
from .pdf_text import layer_quality

MIN_CHARS_PER_PAGE = 120
MAX_CORRUPTION = 0.02        # >2% impossible characters means a broken CMap
MIN_ARABIC_SHARE = 0.35      # an Arabic page whose layer is mostly Latin is suspect


@dataclass
class Route:
    mode: str            # "digital" | "font_repair" | "ocr"
    reason: str
    quality: dict


MIN_GLYPH_COVERAGE = 0.80    # below this, font repair is not worth trusting
MIN_WORD_VALIDITY = 0.50     # share of Arabic words that must be real words


def route_page(lines: List[Line], expect_arabic: bool = True,
               glyph_coverage: float | None = None,
               corrector=None) -> Route:
    """Choose a front-end for one page.

    Three outcomes, not two. Between "the text layer is fine" and "rasterise
    and OCR" sits the case that matters most for Arabic: the text layer is
    unusable but the *glyphs* are intact and the font is embedded, so the real
    characters can be read straight out of the font. That path is exact, where
    OCR on the same page costs about 7% CER.
    """
    q = layer_quality(lines)
    if q["chars"] < MIN_CHARS_PER_PAGE:
        return Route("ocr", f"text layer too thin ({q['chars']} chars)", q)

    # The character-class check above catches a text layer that decodes to
    # Latin-Extended junk. It cannot catch the worse case, where a broken
    # ToUnicode map produces *valid Arabic letters* in the wrong places -
    # 'التفوق' arriving as 'التفػؽ' scores 0% corruption while being unreadable.
    # Only a dictionary sees that, so word validity is the real trust test.
    if corrector is not None and getattr(corrector, "available", False):
        text = " ".join(l.text for l in lines)
        validity = corrector.coverage(text)
        q["word_validity"] = round(validity, 4)
        if validity < MIN_WORD_VALIDITY:
            if glyph_coverage is not None and glyph_coverage >= MIN_GLYPH_COVERAGE:
                return Route("font_repair",
                             f"text layer decodes to non-words "
                             f"({validity:.0%} valid), repaired from embedded font "
                             f"({glyph_coverage:.0%} glyphs)", q)
            return Route("ocr",
                         f"text layer decodes to non-words ({validity:.0%} valid)", q)
    if q["corruption"] > MAX_CORRUPTION:
        if glyph_coverage is not None and glyph_coverage >= MIN_GLYPH_COVERAGE:
            return Route("font_repair",
                         f"text layer corrupt ({q['corruption']:.1%}), "
                         f"repaired from embedded font ({glyph_coverage:.0%} glyphs)", q)
        return Route("ocr", f"text layer corrupt ({q['corruption']:.1%} impossible chars)", q)
    if expect_arabic and q["arabic_share"] < MIN_ARABIC_SHARE:
        if glyph_coverage is not None and glyph_coverage >= MIN_GLYPH_COVERAGE:
            return Route("font_repair",
                         f"little Arabic in layer ({q['arabic_share']:.1%}), "
                         f"repaired from embedded font ({glyph_coverage:.0%} glyphs)", q)
        return Route("ocr", f"little Arabic in layer ({q['arabic_share']:.1%})", q)
    return Route("digital", "text layer trusted", q)
